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

        # Only write to garm relation when image UUID is available (per AC:
        # "Information should only be populated AFTER an image has been created").
        if state.image_id is not None:
            garm_relation = self.model.get_relation(GARM_RELATION_NAME)
            if garm_relation is not None:
                pc = state.provider_config
                gc = state.github_app_config
                sc = state.scaleset_config

                # Remove stale optional keys before writing — old config values
                # (e.g. scaleset_repo when switching to scaleset_org) must not
                # linger in the relation databag alongside the new ones.
                for stale_key in ("scaleset_repo", "scaleset_org"):
                    garm_relation.data[self.unit].pop(stale_key, None)
                garm_relation.data[self.unit].pop("scaleset_pre_install_scripts", None)

                # Only write secret URI if we managed to create the secret
                # (i.e. this unit is the leader). Non-leader units skip.
                password_secret = self._ensure_relation_secret(
                    garm_relation,
                    "configurator-password",
                    pc.password,
                )
                github_key_secret = self._ensure_relation_secret(
                    garm_relation,
                    "configurator-github-key",
                    gc.private_key,
                )

                if password_secret is not None and github_key_secret is not None:
                    garm_relation.data[self.unit].update(
                        {
                            "openstack_auth_url": pc.auth_url,
                            "openstack_username": pc.username,
                            "openstack_password_secret_uri": str(password_secret),
                            "openstack_project_name": pc.project_name,
                            "openstack_user_domain_name": pc.user_domain_name,
                            "openstack_project_domain_name": pc.project_domain_name,
                            "openstack_region_name": pc.region_name,
                            "openstack_network": pc.network,
                            "github_client_id": gc.client_id,
                            "github_installation_id": gc.installation_id,
                            "github_private_key_secret_uri": str(github_key_secret),
                            "scaleset_name": sc.name,
                            "scaleset_flavor": sc.flavor,
                            "scaleset_os_arch": sc.os_arch,
                            "scaleset_min_idle_runner": str(sc.min_idle_runner),
                            "scaleset_max_runner": str(sc.max_runner),
                            "scaleset_labels": sc.labels,
                            "scaleset_runner_group": sc.runner_group,
                            "image_id": state.image_id,
                        }
                    )
                    if sc.repo is not None:
                        garm_relation.data[self.unit]["scaleset_repo"] = sc.repo
                    if sc.org is not None:
                        garm_relation.data[self.unit]["scaleset_org"] = sc.org
                    if sc.pre_install_scripts is not None:
                        garm_relation.data[self.unit]["scaleset_pre_install_scripts"] = (
                            sc.pre_install_scripts
                        )

        if relation is None:
            self.unit.status = ops.WaitingStatus("Waiting for image builder relation")
        elif state.image_id is None:
            self.unit.status = ops.WaitingStatus("Waiting for image UUID from image builder")
        else:
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
            # Non-leader units cannot create secrets; skip silently.
            # The leader unit will handle secret creation on the next reconcile.
            return None

        # Try to find or create the secret.
        try:
            secret = self.model.get_secret(label=secret_name)
            secret.set_content({"value": value})
        except ops.SecretNotFoundError:
            secret = self.app.add_secret({"value": value}, label=secret_name)

        # Grant the secret to the related application so it can read it.
        secret.grant(relation)

        return secret


if __name__ == "__main__":
    ops.main(GarmConfiguratorCharm)
