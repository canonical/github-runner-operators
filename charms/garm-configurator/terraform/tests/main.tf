# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

locals {
  garm_configurator_app_name = "garm-configurator"
  juju_model_name            = "stg-deploy-garm-configurator"
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

data "juju_model" "garm_configurator" {
  name  = local.juju_model_name
  owner = "admin"
}

provider "juju" {}

module "garm_configurator" {
  source     = "./.."
  app_name   = local.garm_configurator_app_name
  channel    = var.channel
  model_uuid = data.juju_model.garm_configurator.uuid
  revision   = var.revision
}

output "app_name" {
  description = "The name of the deployed garm-configurator charm application."
  value       = module.garm_configurator.app_name
}
