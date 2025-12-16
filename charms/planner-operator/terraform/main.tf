# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "github_runner_planner" {
  name       = var.app_name
  model_uuid = var.model_uuid

  charm {
    name     = "github-runner-planner"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  config             = var.config
  constraints        = var.constraints
  units              = var.units
  storage_directives = var.storage
}
