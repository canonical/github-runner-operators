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

provider "juju" {}

module "github_runner_webhook_gateway" {
  source   = "./.."
  app_name = "github_runner_webhook_gateway"
  channel  = var.channel
  model    = "prod-github_runner_webhook_gateway-example"
  revision = var.revision
  config   = { webhook-secret = "" }
}

output "app_name" {
  description = "The name of the deployed github_runner_webhook_gateway charm application."
  value       = module.github_runner_webhook_gateway.app_name
}

output "endpoints" {
  description = "Integration endpoints exposed by github_runner_webhook_gateway charm."
  value       = module.github_runner_webhook_gateway.endpoints
}