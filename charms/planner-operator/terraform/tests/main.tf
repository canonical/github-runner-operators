# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

locals {
  planner_app_name     = "github-runner-planner"
  planner_metrics_port = 9464
  juju_model_name      = "stg-deploy-planner"
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

variable "admin_token_value" {
  description = "Planner admin token value for tests."
  type        = string
  sensitive   = true
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

data "juju_model" "planner" {
  name  = local.juju_model_name
  owner = "admin"
}

resource "juju_application" "rabbitmq" {
  name       = "rabbitmq"
  model_uuid = data.juju_model.planner.uuid

  charm {
    name    = "rabbitmq-k8s"
    channel = "3.12/edge"
  }

  trust       = true
  config      = {}
  constraints = ""
  units       = 1
}

resource "juju_integration" "planner_rabbitmq" {
  model_uuid = data.juju_model.planner.uuid
  application {
    name = local.planner_app_name
  }
  application {
    name = juju_application.rabbitmq.name
  }
}

resource "juju_application" "postgresql" {
  name       = "postgresql"
  model_uuid = data.juju_model.planner.uuid

  charm {
    name    = "postgresql-k8s"
    channel = "16/edge"
  }

  trust       = true
  config      = {}
  constraints = ""
  units       = 1
}

resource "juju_integration" "planner_postgresql" {
  model_uuid = data.juju_model.planner.uuid
  application {
    name = local.planner_app_name
  }
  application {
    name = juju_application.postgresql.name
  }
}

provider "juju" {}

module "github_runner_planner" {
  source            = "./.."
  app_name          = local.planner_app_name
  channel           = var.channel
  model_uuid        = data.juju_model.planner.uuid
  revision          = var.revision
  admin_token_value = var.admin_token_value
  config = {
    metrics-port = local.planner_metrics_port
  }
}

output "app_name" {
  description = "The name of the deployed github_runner_planner charm application."
  value       = module.github_runner_planner.app_name
}

output "endpoints" {
  description = "Integration endpoints exposed by github_runner_planner charm."
  value       = module.github_runner_planner.endpoints
}
