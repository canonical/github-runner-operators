# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "github_runner_webhook_gateway" {
  name  = var.app_name
  model = var.model

  charm {
    name     = "github-runner-webhook-gateway"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  config             = var.config
  constraints        = var.constraints
  units              = var.units
  storage_directives = var.storage
}

resource "juju_application" "rabbitmq" {
  name  = "rabbitmq"
  model = var.model

  charm {
    name     = "rabbitmq-k8s"
    channel  = "3.12/stable"
    revision = var.revision
  }

  trust       = true
  config      = var.config
  constraints = var.constraints
  units       = var.units
}
