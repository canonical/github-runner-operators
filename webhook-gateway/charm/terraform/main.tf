# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "github_runner_webhook_gateway" {
  name  = var.app_name
  model = var.model

  charm {
    name     = "github_runner_webhook_gateway"
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
    name     = "rabbitmq_server"
    channel  = "3.12/stable"
    revision = 247
  }

  config      = var.config
  constraints = "arch=amd64 cores=4 mem=4096M root-disk=51200M" # according to https://www.rabbitmq.com/docs/production-checklist#minimum-hardware 4 cpu 4 GiB of Ram are recommended
  units       = var.units

  expose {}
}


resource "juju_offer" "rabbitmq_amqp" {
  model            = var.model
  application_name = juju_application.rabbitmq.name
  endpoints        = ["amqp"]
  name             = "rabbitmq"
}

resource "juju_access_offer" "this" {
  offer_url = juju_offer.rabbitmq_amqp.url
  consume   = ["k8s-prod-github-runner-github-runner"]
  admin     = [var.model]
}