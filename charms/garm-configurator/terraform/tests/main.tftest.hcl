# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variables {
  channel = "latest/edge"
  # renovate: depName="garm_configurator"
  revision = 1
}

run "basic_deploy" {
  assert {
    condition     = module.garm_configurator.app_name == "garm-configurator"
    error_message = "garm-configurator app_name did not match expected"
  }
}
