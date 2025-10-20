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

resource "juju_secret" "webhook-gateway-secret" {
  model = "prod-github_runner_webhook_gateway-example"
  name  = "webhook-gateway"
  value = {
    value = data.vault_generic_secret.webhook-gateway.data["webhook_secret"]
  }
  info = "The webhook gateway secret used for validating the webhooks"
}

provider "juju" {}

module "github_runner_webhook_gateway" {
  source   = "./.."
  app_name = "github_runner_webhook_gateway"
  channel  = var.channel
  model    = "prod-github_runner_webhook_gateway-example"
  revision = var.revision
  config = {
    webhook-secret = juju_secret.webhook-gateway-secret.secret_uri
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