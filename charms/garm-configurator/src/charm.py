#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm entrypoint for the GARM configurator charm."""

import json
import logging
import typing

import ops
from garm_configurator_relation import ConfiguratorApplicationData
from garm_configurator_relation import ProviderConfig as RelationProviderConfig
from garm_configurator_relation import ScalesetConfig as RelationScalesetConfig

from charm_state import (
    GARM_RELATION_NAME,
    IMAGE_RELATION_NAME,
    CharmConfigInvalidError,
    CharmState,
)

logger = logging.getLogger(__name__)


class GarmConfiguratorCharm(ops.CharmBase):
    """GARM configurator charm."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)
        for event in [
            self.on.config_changed,
            self.on.secret_changed,
            self.on[GARM_RELATION_NAME].relation_joined,
            self.on[GARM_RELATION_NAME].relation_changed,
            self.on[IMAGE_RELATION_NAME].relation_joined,
            self.on[IMAGE_RELATION_NAME].relation_changed,
            self.on[IMAGE_RELATION_NAME].relation_broken,
        ]:
            self.framework.observe(event, self._reconcile)

    def _reconcile(self, event: ops.EventBase) -> None:
        """Handle all charm events by reconciling configuration and relation data.

        Blocks non-leader units, because only the leader may write the application databag
        and provision the credential secrets. On the leader, reads the current charm state,
        forwards OpenStack credentials to the image-builder relation, publishes the complete
        scaleset configuration (with secrets) to the garm-configurator relations' application
        databags once every required value, including the image, is available, then sets unit
        status to reflect readiness.

        Args:
            event: The triggering event.
        """
        if not self.unit.is_leader():
            self.unit.status = ops.BlockedStatus("Only the leader unit publishes relation data")
            return

        try:
            state = CharmState.from_charm(self)
        except CharmConfigInvalidError as e:
            # Juju shows only the first line of a status message, so log the full
            # detail (a pydantic error may span several lines) for debug-log.
            logger.warning("Invalid charm config:\n%s", e.msg)
            self.unit.status = ops.BlockedStatus(e.msg)
            return

        self._update_image_relation(state)
        self._configure_garm_relation(state)

        if state.image_overrides_builder:
            self.unit.status = ops.ActiveStatus("Ready; configured image overrides image builder")
        elif state.image is not None:
            self.unit.status = ops.ActiveStatus("Ready")
        elif state.image_relation is None:
            self.unit.status = ops.BlockedStatus("Missing image config or image builder relation")
        else:
            self.unit.status = ops.WaitingStatus("Waiting for image UUID from image builder")

    def _update_image_relation(self, state: CharmState) -> None:
        """Push OpenStack provider credentials to the image-builder relation.

        Does nothing if the image-builder relation is not yet joined.

        Args:
            state: Current resolved charm state.
        """
        relation = state.image_relation
        if relation is None:
            return
        relation.data[self.unit].update(
            {
                "auth_url": state.provider_config.auth_url,
                "password": state.provider_config.password,
                "project_domain_name": state.provider_config.project_domain_name,
                "project_name": state.provider_config.project_name,
                "user_domain_name": state.provider_config.user_domain_name,
                "username": state.provider_config.username,
            }
        )

    def _ensure_relation_secret(
        self,
        relation: ops.Relation,
        secret_name: str,
        value: str,
    ) -> ops.Secret | None:
        """Ensure a Juju secret exists for the given value and grant it to the related app.

        Creates a new secret if none exists on this unit for ``secret_name``,
        updates its content if it exists, and grants read access to the
        related application so it can retrieve the secret via its URI.

        Args:
            relation: The garm-configurator relation.
            secret_name: A per-application name for the secret (used as Juju label).
            value: The secret value to store.

        Returns:
            The (possibly newly-created) Juju Secret object, or None if this
            unit is not the leader.
        """
        if not self.unit.is_leader():
            return None

        try:
            secret = self.model.get_secret(label=secret_name)
            secret.set_content({"value": value})
        except ops.SecretNotFoundError:
            secret = self.app.add_secret({"value": value}, label=secret_name)

        secret.grant(relation)

        return secret

    def _configure_garm_relation(self, state: CharmState) -> None:
        """Publish the complete configurator payload to the garm-configurator relation.

        Builds a ``ConfiguratorApplicationData`` nesting the provider and GitHub App credentials
        under ``provider`` and the scaleset fields, runner options, and image reference under
        ``scaleset``, then writes it to the application databag with a single
        ``ops.Relation.save`` call. ``Relation.save`` persists every model field, so an unset
        optional provider field is published as null and an unset scaleset field as an empty
        string rather than omitted; consumers treat both as "unset". The ``image_id`` field
        carries either an OpenStack image name or ID for compatibility.

        Also provisions Juju secrets for the OpenStack password and GitHub App private key and
        writes their secret URIs alongside the credential fields. Only the leader reaches this
        method, because ``_reconcile`` blocks non-leader units: they cannot create the secrets
        and must not write the application databag.

        The relation contract marks the fields that block provider or scaleset creation as
        required. The configurator therefore publishes nothing until every one of them is
        available: while the image builder has not supplied an image yet, it withdraws any
        previously published payload instead of writing one the consumer would reject as
        incomplete.

        Does nothing when no garm-configurator relation is joined yet. Status reporting is
        handled by the caller (_reconcile).

        Args:
            state: Current resolved charm state.
        """
        garm_relation = self.model.get_relation(GARM_RELATION_NAME)
        if garm_relation is None:
            return
        if state.image is None:
            self._withdraw_garm_relation(garm_relation)
            return

        password_secret = self._ensure_relation_secret(
            garm_relation,
            "configurator-password",
            state.provider_config.password,
        )
        github_key_secret = self._ensure_relation_secret(
            garm_relation,
            "configurator-github-key",
            state.github_app_config.private_key,
        )
        if password_secret is None or github_key_secret is None:
            return

        pre_install = state.scaleset_config.pre_install_scripts
        rc = state.runner_config
        scaleset_data: dict[str, str] = {
            "name": state.scaleset_config.name,
            "provider_name": state.provider_config.provider_name,
            "image_id": state.image,
            "image_visibility": state.scaleset_config.image_visibility or "",
            "security_group": state.scaleset_config.security_group,
            "flavor": state.scaleset_config.flavor,
            "os_arch": state.scaleset_config.os_arch,
            "min_idle_runner": str(state.scaleset_config.min_idle_runner),
            "max_runner": str(state.scaleset_config.max_runner),
            "labels": state.scaleset_config.labels,
            "runner_group": state.scaleset_config.runner_group,
            "enable_shell": str(state.scaleset_config.enable_shell).lower(),
            "pre_install_scripts": json.dumps({"pre_install.sh": pre_install})
            if pre_install
            else "",
            "org": state.scaleset_config.org or "",
            "repo": state.scaleset_config.repo or "",
            "dockerhub_mirror": rc.dockerhub_mirror or "",
            "runner_http_proxy": rc.runner_http_proxy or "",
            "aproxy_exclude_addresses": rc.aproxy_exclude_addresses or "",
            "aproxy_redirect_ports": rc.aproxy_redirect_ports or "",
            "otel_collector_endpoint": rc.otel_collector_endpoint or "",
            "pre_job_script": rc.pre_job_script or "",
        }

        garm_relation.save(
            ConfiguratorApplicationData(
                provider=RelationProviderConfig(
                    openstack_auth_url=state.provider_config.auth_url,
                    openstack_username=state.provider_config.username,
                    openstack_password_secret_uri=str(password_secret.id),
                    openstack_project_name=state.provider_config.project_name,
                    openstack_user_domain_name=state.provider_config.user_domain_name,
                    openstack_project_domain_name=state.provider_config.project_domain_name,
                    openstack_region_name=state.provider_config.region_name,
                    openstack_network=state.provider_config.network,
                    github_app_id=state.github_app_config.app_id,
                    github_installation_id=state.github_app_config.installation_id,
                    github_private_key_secret_uri=str(github_key_secret.id),
                ),
                scaleset=RelationScalesetConfig(**scaleset_data),
            ),
            self.app,
        )

    def _withdraw_garm_relation(self, relation: ops.Relation) -> None:
        """Remove this application's payload from the garm-configurator relation.

        Used while a required value, such as the runner image, is not available. Leaving an
        older payload in place would keep publishing a configuration the operator has already
        changed, and writing a partial one would make the consumer reject the relation.

        Args:
            relation: The garm-configurator relation to withdraw from.
        """
        if relation.data[self.app]:
            logger.info(
                "Withdrawing garm-configurator relation data until required values are available"
            )
            relation.data[self.app].clear()


if __name__ == "__main__":
    ops.main(GarmConfiguratorCharm)
