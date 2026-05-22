#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm entrypoint for the GARM configurator charm."""

import logging
import typing

import ops

logger = logging.getLogger(__name__)


class GarmConfiguratorCharm(ops.CharmBase):
    """GARM configurator charm."""

    def __init__(self, *args: typing.Any) -> None:
        """Initialize the instance.

        Args:
            args: passthrough to CharmBase.
        """
        super().__init__(*args)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Handle collect-unit-status event.

        Args:
            event: The collect status event.
        """
        event.add_status(ops.ActiveStatus("Ready"))


if __name__ == "__main__":
    ops.main(GarmConfiguratorCharm)
