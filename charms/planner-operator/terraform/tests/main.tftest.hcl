# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

variables {
  channel = "latest/edge"
  # renovate: depName="github_runner_planner"
  revision = 1
}

run "basic_deploy" {
  assert {
    condition     = module.github_runner_planner.app_name == "github-runner-planner"
    error_message = "github-runner-planner app_name did not match expected"
  }

  assert {
    condition     = juju_application.rabbitmq.name == "rabbitmq"
    error_message = "rabbitmq name did not match expected"
  }

  assert {
    condition     = contains([for app in juju_integration.planner_rabbitmq.application : app.name], "rabbitmq")
    error_message = "Integration must include the rabbitmq application"
  }

  assert {
    condition     = contains([for app in juju_integration.planner_rabbitmq.application : app.name], "github-runner-planner")
    error_message = "Integration must include the planner application"
  }

  assert {
    condition     = juju_application.postgresql.name == "postgresql"
    error_message = "postgresql name did not match expected"
  }

  assert {
    condition     = contains([for app in juju_integration.planner_postgresql.application : app.name], "postgresql")
    error_message = "Integration must include the postgresql application"
  }

  assert {
    condition     = contains([for app in juju_integration.planner_postgresql.application : app.name], "github-runner-planner")
    error_message = "Integration must include the planner application"
  }
}
