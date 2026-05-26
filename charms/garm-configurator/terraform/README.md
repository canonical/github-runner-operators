# GARM configurator terraform module

This folder contains a base [Terraform][Terraform] module for the GARM configurator charm.

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

## Using garm_configurator base module in higher level modules

If you want to use `garm_configurator` base module as part of your Terraform module, import it
like shown below:

```text
data "juju_model" "my_model" {
  name = "test-deploy-garm-configurator"
  owner = "admin"
}

module "garm_configurator" {
  source = "git::https://github.com/canonical/github-runner-operators//charms/garm-configurator/terraform"

  model_uuid = data.juju_model.my_model.uuid
  # (Customize configuration variables here if needed)
}
```

[Terraform]: https://developer.hashicorp.com/terraform
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
[Juju]: https://juju.is
[garm_configurator-integrations]: https://charmhub.io/garm-configurator/integrations
