#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm entrypoint for the GARM configurator charm."""

import json
import typing

import ops

from charm_state import (
    GARM_RELATION_NAME,
    IMAGE_RELATION_NAME,
    CharmConfigInvalidError,
    CharmState,
)


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

        Reads the current charm state, forwards OpenStack credentials to the
        image-builder relation, publishes scaleset configuration (and secrets
        when the image UUID is available) to all garm-configurator relations,
        then sets unit status to reflect readiness.

        Args:
            event: The triggering event.
        """
        try:
            state = CharmState.from_charm(self)
        except CharmConfigInvalidError as e:
            self.unit.status = ops.BlockedStatus(e.msg)
            return

        self._update_image_relation(state)
        self._configure_garm_relation(state)

        if self.model.get_relation(IMAGE_RELATION_NAME) is None:
            self.unit.status = ops.WaitingStatus("Waiting for image builder relation")
        elif state.image_id is None:
            self.unit.status = ops.WaitingStatus("Waiting for image UUID from image builder")
        else:
            self.unit.status = ops.ActiveStatus("Ready")

    def _update_image_relation(self, state: CharmState) -> None:
        """Push OpenStack provider credentials to the image-builder relation.

        Does nothing if the image-builder relation is not yet joined.

        Args:
            state: Current resolved charm state.
        """
        relation = self.model.get_relation(IMAGE_RELATION_NAME)
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
            secret_name: A per-unit name for the secret (used as Juju label).
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
        """Publish scaleset configuration to the garm-configurator relation.

        Writes non-secret scaleset fields (name, provider, credentials, image,
        flavor, arch, runner counts, labels, runner group, and pre-install
        scripts) to the relation. The optional ``org`` and ``repo`` fields are
        included only when set.

        When the image UUID is present and this unit holds leadership, also
        provisions Juju secrets for the OpenStack password and GitHub App
        private key, then writes the full OpenStack provider and GitHub App
        credential fields alongside their secret URIs.

        Does nothing when no garm-configurator relation is joined yet or when
        secrets cannot be created (non-leader unit). Status reporting is
        handled by the caller (_reconcile).

        Args:
            state: Current resolved charm state.
        """
        garm_relation = self.model.get_relation(GARM_RELATION_NAME)
        if garm_relation is None:
            return

        pre_install = state.scaleset_config.pre_install_scripts
        basic_data: dict[str, str] = {
            "name": state.scaleset_config.name,
            "provider_name": state.provider_config.provider_name,
            "image_id": state.image_id or "",
            "flavor": state.scaleset_config.flavor,
            "os_arch": state.scaleset_config.os_arch,
            "min_idle_runner": str(state.scaleset_config.min_idle_runner),
            "max_runner": str(state.scaleset_config.max_runner),
            "labels": state.scaleset_config.labels,
            "runner_group": state.scaleset_config.runner_group,
            "pre_install_scripts": json.dumps({"pre_install.sh": pre_install})
            if pre_install
            else "",
        }
        if state.scaleset_config.org:
            basic_data["org"] = state.scaleset_config.org
        if state.scaleset_config.repo:
            basic_data["repo"] = state.scaleset_config.repo
        garm_relation.data[self.unit].update(basic_data)

        if state.image_id is None:
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

        garm_relation.data[self.unit].update(
            {
                "openstack_auth_url": state.provider_config.auth_url,
                "openstack_username": state.provider_config.username,
                "openstack_password_secret_uri": password_secret.id,
                "openstack_project_name": state.provider_config.project_name,
                "openstack_user_domain_name": state.provider_config.user_domain_name,
                "openstack_project_domain_name": state.provider_config.project_domain_name,
                "openstack_region_name": state.provider_config.region_name,
                "openstack_network": state.provider_config.network,
                "github_client_id": state.github_app_config.client_id,
                "github_app_id": state.github_app_config.app_id,
                "github_installation_id": state.github_app_config.installation_id,
                "github_private_key_secret_uri": github_key_secret.id,
                "image_id": state.image_id,
            }
        )


if __name__ == "__main__":
    ops.main(GarmConfiguratorCharm)
