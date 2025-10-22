# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variable "channel" {
  description = "The channel to use when deploying a charm."
  type        = string
  default     = "latest/edge"
}

variable "revision" {
  description = "Revision number of the charm."
  type        = number
  default     = null
}

terraform {
  required_providers {
    juju = {
      version = "~> 0.23.0"
      source  = "juju/juju"
    }
  }
}

resource "juju_model" "webhook" {
  name = "test-deploy-webhook"
}

resource "juju_application" "rabbitmq" {
  name  = "rabbitmq"
  model = juju_model.webhook.name

  charm {
    name     = "rabbitmq-k8s"
    channel  = "3.12/stable"
    revision = var.revision
  }

  trust       = true
  config      = {}
  constraints = ""
  units       = 1
}

resource "juju_secret" "webhook_gateway_secret" {
  model = juju_model.webhook.name
  name  = "webhook-gateway"
  value = { value = data.vault_generic_secret.webhook_gateway.data["webhook_secret"] }
  info  = "The webhook gateway secret used for validating the webhooks"
}

resource "juju_access_secret" "webhook_gateway_access" {
  applications = ["github-runner-webhook-gateway"]
  model        = juju_model.webhook.name
  secret_id    = juju_secret.webhook_gateway_secret.secret_id
}

provider "juju" {}

module "github_runner_webhook_gateway" {
  source   = "./.."
  app_name = "github_runner_webhook_gateway"
  channel  = var.channel
  model    = juju_model.webhook.name
  revision = var.revision
  config = {
    webhook-secret = juju_secret.webhook_gateway_secret.secret_uri,
    metrics-port   = 9464
  }
}

output "app_name" {
  description = "The name of the deployed github_runner_webhook_gateway charm application."
  value       = module.github_runner_webhook_gateway.app_name
}

output "endpoints" {
  description = "Integration endpoints exposed by github_runner_webhook_gateway charm."
  value       = module.github_runner_webhook_gateway.endpoints
}
