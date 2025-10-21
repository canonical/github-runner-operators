# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

data "vault_generic_secret" "webhook_gateway" {
  path = "secret/prodstack6/roles/stg-ps6-github-runner-k8s-shared/webhook-gateway"
}

