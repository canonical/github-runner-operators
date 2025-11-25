# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

locals {
  webhook_gateway_app_name     = "github-runner-webhook-gateway"
  webhook_gateway_metrics_port = 9464
  juju_model_name              = "stg-deploy-webhook-gateway"
}

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
  required_version = ">= 1.6.6"
  required_providers {
    juju = {
      source  = "juju/juju"
      version = ">= 1.0.0"
    }
  }
}

data "juju_model" "webhook" {
  name  = local.juju_model_name
  owner = "admin"
}

resource "juju_application" "rabbitmq" {
  name       = "rabbitmq"
  model_uuid = data.juju_model.webhook.uuid

  charm {
    name    = "rabbitmq-k8s"
    channel = "3.12/stable"
  }

  trust       = true
  config      = {}
  constraints = ""
  units       = 1
}

resource "juju_integration" "webhook_rabbitmq" {
  model_uuid = data.juju_model.webhook.uuid
  application {
    name = local.webhook_gateway_app_name
  }
  application {
    name = juju_application.rabbitmq.name
  }
}

provider "juju" {}

module "github_runner_webhook_gateway" {
  source     = "./.."
  app_name   = local.webhook_gateway_app_name
  channel    = var.channel
  model_uuid = data.juju_model.webhook.uuid
  revision   = var.revision
  config = {
    metrics-port = local.webhook_gateway_metrics_port
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
