# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.github_runner_garm.name
}

output "database_passphrase_secret_id" {
  description = "ID of the Juju secret containing the GARM database encryption passphrase, when configured."
  value       = try(juju_secret.garm_database_passphrase[0].secret_id, null)
  sensitive   = true
}

output "endpoints" {
  description = "Integration endpoints required by the GARM charm."
  value = {
    postgresql = "postgresql"
  }
}
