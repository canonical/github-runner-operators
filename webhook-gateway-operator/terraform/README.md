# GitHub runner webhook gateway terraform module

This folder contains a base [Terraform][Terraform] module for the GitHub runner webhook gateway charm.

The module uses the [Terraform Juju provider][Terraform Juju provider] to model the charm
deployment onto any Kubernetes environment managed by [Juju][Juju].

## Module structure

- **main.tf** - Defines the Juju application to be deployed.
- **variables.tf** - Allows customization of the deployment. Also models the charm configuration,
  except for exposing the deployment options (Juju model name, channel or application name).
- **output.tf** - Integrates the module with other Terraform modules, primarily
  by defining potential integration endpoints (charm integrations), but also by exposing
  the Juju application name.
- **versions.tf** - Defines the Terraform provider version.

## Using github_runner_webhook_gateway base module in higher level modules

If you want to use `github_runner_webhook_gateway` base module as part of your Terraform module, import it
like shown below:

```text
data "juju_model" "my_model" {
  name = "test-deploy-webhook-gateway"
  owner = "admin"
}

module "github_runner_webhook_gateway" {
  source = "git::https://github.com/canonical/github-runner-operators/tree/main/webhook-gateway/charm/terraform"

  model_uuid = data.juju_model.my_model.uuid
  # (Customize configuration variables here if needed)
}
```

Create integrations, for instance:

```text
resource "juju_integration" "webhook_rabbitmq" {
  model_uuid = data.juju_model.my_model.uuid
  application {
    name     = module.github_runner_webhook_gateway.app_name
  }
  application {
    name = "rabbitmq"
  }
}
```

The complete list of available integrations can be found [in the Integrations tab][github_runner_webhook_gateway-integrations].

[Terraform]: https://developer.hashicorp.com/terraform
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
[Juju]: https://juju.is
[github_runner_webhook_gateway-integrations]: https://charmhub.io/github_runner_webhook_gateway/integrations
