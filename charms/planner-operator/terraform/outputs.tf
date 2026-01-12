# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.github_runner_planner.name
}

output "endpoints" {
  value = {
    rabbitmq   = "rabbitmq"
    postgresql = "postgresql"
  }
}

output "admin_token_secret_id" {
  description = "ID of the created Juju secret that stores the planner admin token."
  value       = juju_secret.planner_admin_token.id
  sensitive   = true
}
