#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm entrypoint for the GARM configurator charm."""

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
            self.on[IMAGE_RELATION_NAME].relation_joined,
            self.on[IMAGE_RELATION_NAME].relation_changed,
            self.on[IMAGE_RELATION_NAME].relation_broken,
            self.on[GARM_RELATION_NAME].relation_joined,
            self.on[GARM_RELATION_NAME].relation_changed,
        ]:
            self.framework.observe(event, self._reconcile)

    def _reconcile(self, event: ops.EventBase) -> None:
        """Reconcile all charm state for every event.

        Reads full current state and acts idempotently: forwards OpenStack
        credentials to the image builder relation, and reports unit status.

        Args:
            event: The triggering event.
        """
        try:
            state = CharmState.from_charm(self)
        except CharmConfigInvalidError as e:
            self.unit.status = ops.BlockedStatus(e.msg)
            return

        relation = self.model.get_relation(IMAGE_RELATION_NAME)
        if relation is not None:
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

        if relation is None:
            self.unit.status = ops.WaitingStatus("Waiting for image builder relation")
            return
        elif state.image_id is None:
            self.unit.status = ops.WaitingStatus("Waiting for image UUID from image builder")
            return
        self._configure_garm_relation(state)
        self.unit.status = ops.ActiveStatus("Ready")

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
        """Populate the garm-configurator relation data when image_id is present.

        Reads the garm relation, creates or updates the required secrets,
        and writes all configuration fields. Returns silently if the garm
        relation or secrets are not yet available — status reporting is
        handled by the caller (_reconcile).
        """
        garm_relation = self.model.get_relation(GARM_RELATION_NAME)
        if garm_relation is None:
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
        
        for key, value in {
            "scaleset_repo": state.scaleset_config.repo,
            "scaleset_org": state.scaleset_config.org,
            "scaleset_pre_install_scripts": state.scaleset_config.pre_install_scripts,
        }.items():
            if value is not None:
                garm_relation.data[self.unit][key] = value
            else:
                garm_relation.data[self.unit].pop(key, None)

        garm_relation.data[self.unit].update(
            {
                "openstack_auth_url": state.provider_config.auth_url,
                "openstack_username": state.provider_config.username,
                "openstack_password_secret_uri": str(password_secret),
                "openstack_project_name": state.provider_config.project_name,
                "openstack_user_domain_name": state.provider_config.user_domain_name,
                "openstack_project_domain_name": state.provider_config.project_domain_name,
                "openstack_region_name": state.provider_config.region_name,
                "openstack_network": state.provider_config.network,
                "github_client_id": state.github_app_config.client_id,
                "github_installation_id": state.github_app_config.installation_id,
                "github_private_key_secret_uri": str(github_key_secret),
                "scaleset_name": state.scaleset_config.name,
                "scaleset_flavor": state.scaleset_config.flavor,
                "scaleset_os_arch": state.scaleset_config.os_arch,
                "scaleset_min_idle_runner": str(state.scaleset_config.min_idle_runner),
                "scaleset_max_runner": str(state.scaleset_config.max_runner),
                "scaleset_labels": state.scaleset_config.labels,
                "scaleset_runner_group": state.scaleset_config.runner_group,
                "image_id": state.image_id,
            }
        )


if __name__ == "__main__":
    ops.main(GarmConfiguratorCharm)
