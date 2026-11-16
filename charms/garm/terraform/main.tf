# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "github_runner_garm" {
  name       = var.app_name
  model_uuid = var.model_uuid

  charm {
    name     = "garm"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  config = merge(
    var.config,
    var.database_passphrase == null
    ? {}
    : { "database-passphrase" = juju_secret.garm_database_passphrase[0].secret_uri },
  )
  constraints = var.constraints
  units       = var.units
}

resource "juju_secret" "garm_database_passphrase" {
  count      = var.database_passphrase == null ? 0 : 1
  model_uuid = var.model_uuid
  name       = "garm_database_passphrase"
  value = {
    value = var.database_passphrase
  }
  info = "GARM database encryption passphrase"
}

resource "juju_access_secret" "garm_database_passphrase" {
  count        = var.database_passphrase == null ? 0 : 1
  model_uuid   = var.model_uuid
  secret_id    = juju_secret.garm_database_passphrase[0].secret_id
  applications = [juju_application.github_runner_garm.name]
}
