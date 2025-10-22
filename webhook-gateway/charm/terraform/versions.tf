# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

terraform {
  required_version = ">= 1.6.6"
  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "~> 4.3.0"
    }

    juju = {
      source  = "juju/juju"
      version = ">= 0.23.0"
    }
  }
}
