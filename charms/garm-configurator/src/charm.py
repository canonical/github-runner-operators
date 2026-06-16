#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm entrypoint for the GARM configurator charm."""

import json
import typing

import ops

from charm_state import IMAGE_RELATION_NAME, CharmConfigInvalidError, CharmState

GARM_CONFIGURATOR_RELATION_NAME = "garm-configurator"


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
            self.on[GARM_CONFIGURATOR_RELATION_NAME].relation_changed,
            self.on[IMAGE_RELATION_NAME].relation_joined,
            self.on[IMAGE_RELATION_NAME].relation_changed,
            self.on[IMAGE_RELATION_NAME].relation_broken,
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

        rc = state.runner_config
        relation_data = {
            "name": state.scaleset_config.name,
            "provider_name": state.provider_name,
            "credentials_name": state.credentials_name,
            "image_id": str(state.image_id),
            "flavor": state.scaleset_config.flavor,
            "os_arch": state.scaleset_config.os_arch,
            "min_idle_runner": str(state.scaleset_config.min_idle_runner),
            "max_runner": str(state.scaleset_config.max_runner),
            "labels": (
                state.scaleset_config.labels
                if isinstance(state.scaleset_config.labels, str)
                else ",".join(state.scaleset_config.labels)
            ),
            "runner_group": state.scaleset_config.runner_group,
            "pre_install_scripts": json.dumps(
                {"pre_install.sh": state.scaleset_config.pre_install_scripts}
                if state.scaleset_config.pre_install_scripts
                else {}
            ),
            "dockerhub_mirror": rc.dockerhub_mirror or "",
            "runner_http_proxy": rc.runner_http_proxy or "",
            "aproxy_exclude_addresses": rc.aproxy_exclude_addresses or "",
            "aproxy_redirect_ports": rc.aproxy_redirect_ports or "",
            "otel_collector_endpoint": rc.otel_collector_endpoint or "",
            "pre_job_script": rc.pre_job_script or "",
        }
        for garm_relation in self.model.relations[GARM_CONFIGURATOR_RELATION_NAME]:
            garm_relation.data[self.unit].update(relation_data)

        if relation is None:
            self.unit.status = ops.WaitingStatus("Waiting for image builder relation")
        elif state.image_id is None:
            self.unit.status = ops.WaitingStatus("Waiting for image UUID from image builder")
        else:
            self.unit.status = ops.ActiveStatus("Ready")


if __name__ == "__main__":
    ops.main(GarmConfiguratorCharm)
