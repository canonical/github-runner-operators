# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for GarmConfiguratorCharm."""

import ops
from scenario import Context, State

from charm import GarmConfiguratorCharm


def test_charm_reaches_active_on_install():
    """
    arrange: A fresh charm context.
    act: Run the install event.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    out = ctx.run(ctx.on.install(), State())
    assert out.unit_status == ops.ActiveStatus("Ready")


def test_charm_reaches_active_on_config_changed():
    """
    arrange: A fresh charm context.
    act: Run the config-changed event.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    out = ctx.run(ctx.on.config_changed(), State())
    assert out.unit_status == ops.ActiveStatus("Ready")


def test_charm_collect_unit_status_emits_active():
    """
    arrange: A fresh charm context.
    act: Run the collect-unit-status event directly.
    assert: Unit status is Active.
    """
    ctx = Context(GarmConfiguratorCharm)
    out = ctx.run(ctx.on.collect_unit_status(), State())
    assert out.unit_status == ops.ActiveStatus("Ready")
