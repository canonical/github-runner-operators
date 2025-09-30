# Contribute

## Overview

This document explains the processes and practices recommended for contributing enhancements to the codebase.

* Generally, before developing enhancements to this code base, you should consider [opening an issue](https://github.com/canonical/github-runner-operator/issues) explaining your use case.
* If you would like to chat with us about your use-cases or proposed implementation, you can reach us at [Canonical Charm Development Matrix public channel](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).
* All enhancements require review before being merged. Code review typically examines
    * code quality
    * test coverage

## Code of conduct

When contributing, you must abide by the
[Ubuntu Code of Conduct](https://ubuntu.com/community/ethos/code-of-conduct).

## Submissions

If you want to address an issue or a bug in this project,
notify in advance the people involved to avoid confusion;
also, reference the issue or bug number when you submit the changes.

- [Fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-forks)
  our [GitHub repository](https://github.com/canonical/github-runner-operators)
  and add the changes to your fork, properly structuring your commits,
  providing detailed commit messages and signing your commits.
- Make sure the updated project builds and runs without warnings or errors;
  this includes linting, documentation, code and tests.
- Submit the changes as a
  [pull request (PR)](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork).

Your changes will be reviewed in due time; if approved, they will be eventually merged.

### Describing pull requests

To be properly considered, reviewed and merged,
your pull request must provide the following details:

- **Title**: Summarize the change in a short, descriptive title.

- **Overview**: Describe the problem that your pull request solves.
  Mention any new features, bug fixes or refactoring.

- **Rationale**: Explain why the change is needed.


- **Checklist**: Complete the following items:

    - The PR is tagged with appropriate label (`urgent`, `trivial`, `senior-review-required`, `documentation`).

### Signing commits

To improve contribution tracking,
we use the [Canonical contributor license agreement](https://assets.ubuntu.com/v1/ff2478d1-Canonical-HA-CLA-ANY-I_v1.2.pdf)
(CLA) as a legal sign-off, and we require all commits to have verified signatures.

### Canonical contributor agreement

Canonical welcomes contributions to this repository. Please check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you’re interested in contributing to the solution.

#### Verified signatures on commits

All commits in a pull request must have cryptographic (verified) signatures.
To add signatures on your commits, follow the
[GitHub documentation](https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits).


## Develop

For any problems with this charm, please [report bugs here](https://github.com/canonical/github-runner-operator/issues).

The code can be downloaded as follows:

```shell
git clone https://github.com/canonical/github-runner-operators.git
```

The code structure is as follows

- `internal/`: Internal libraries for the applications
- `webhook-gateway`: The webhook gateway application and charm code


### Test

This project uses standard Go testing tools for unit tests and integration tests.
You can have a look at the GitHub actions workflows in `.github/workflows/` to see how the tests are run in CI.

Run unit tests using:

```shell
go test -race -v ./...
```

Run `webhook-gateway` integration tests using:

```shell
APP_PORT=8080 WEBHOOK_SECRET=fake RABBITMQ_CONNECT_STRING="amqp://guest:guest@localhost:5672/" go test -cover -v  ./webhook-gateway -integration
```

It assumes you have access to a RabbitMQ server running reachable at $RABBITMQ_CONNECT_STRING.
You can use `docker` to run a RabbitMQ server locally:

```shell
docker run -d  --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4-management
```

### Charm development

The charm uses the [12 factor app pattern](https://canonical-12-factor-app-support.readthedocs-hosted.com/latest/). 
In order to build the webhook-gateway rock, use the
`build-webhook-gateway-rock.sh` script.

The `github-runner-webhook-gateway` charm code is in the `webhook-gateway/charm` directory.

Integration tests for the charm are in the `webhook-gateway/charm_tests` directory.

Have a look at [this tutorial](https://documentation.ubuntu.com/charmcraft/latest/tutorial/kubernetes-charm-go/)
for a step-by-step guide to develop a Kubernetes charm using Go.

To run the charm integration test, the charm file and rock has to be provided as input.
You would need an lxd and microk8s cloud to run the tests. Ensure the `microk8s`
controller is active in your juju client before running the tests. An 
example run command in `webhook-gateway` directory is as follows:

```shell
tox -e integration --  --charm-file ./charm/github-runner-webhook-gateway_amd64.charm --webhook-gateway-image localhost:32000/mayfly:0.1
```

To add the rock to the microk8s registry, use the following command:

```shell
rockcraft.skopeo copy \
  --insecure-policy --dest-tls-verify=false \
  oci-archive:mayfly_0.1_$(dpkg --print-architecture).rock \
  docker://localhost:32000/mayfly:0.1
```