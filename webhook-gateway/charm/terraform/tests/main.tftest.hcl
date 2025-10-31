# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variables {
  channel = "latest/edge"
  # renovate: depName="github_runner_webhook_gateway"
  revision = 1
}

run "basic_deploy" {
  assert {
    condition     = module.github_runner_webhook_gateway.app_name == "github-runner-webhook-gateway"
    error_message = "github-runner-webhook-gateway app_name did not match expected"
  }

  assert {
    condition     = juju_application.rabbitmq.name == "rabbitmq"
    error_message = "rabbitmq name did not match expected"
  }

  assert {
    condition     = contains([for app in juju_integration.webhook_rabbitmq.application : app.name], "rabbitmq")
    error_message = "Integration must include the rabbitmq application"
  }

  assert {
    condition     = contains([for app in juju_integration.webhook_rabbitmq.application : app.name], "github-runner-webhook-gateway")
    error_message = "Integration must include the webhook gateway application"
  }
}
