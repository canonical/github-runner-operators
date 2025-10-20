# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variables {
  channel = "latest/edge"
  # renovate: depName="github_runner_webhook_gateway"
  revision = 1
}

run "basic_deploy" {
  assert {
    condition     = module.github_runner_webhook_gateway.app_name == "github_runner_webhook_gateway"
    error_message = "github_runner_webhook_gateway app_name did not match expected"
  }
}