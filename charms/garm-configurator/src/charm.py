#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm entrypoint for the GARM configurator charm."""

import typing

import ops

from charm_state import CharmConfigInvalidError, CharmState


class GarmConfiguratorCharm(ops.CharmBase):
    """GARM configurator charm."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    def _on_config_changed(self, _event: ops.ConfigChangedEvent) -> None:
        """Validate configuration on config-changed."""
        try:
            CharmState.from_charm(self)
        except CharmConfigInvalidError as e:
            self.unit.status = ops.BlockedStatus(e.msg)
            return

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Handle collect-unit-status event.

        Args:
            event: The collect status event.
        """
        try:
            CharmState.from_charm(self)
        except CharmConfigInvalidError as e:
            self.unit.status = ops.BlockedStatus(e.msg)
            return
        event.add_status(ops.ActiveStatus("Ready"))


if __name__ == "__main__":
    ops.main(GarmConfiguratorCharm)
