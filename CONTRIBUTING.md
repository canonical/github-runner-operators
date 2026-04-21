# Contributing

This document explains the processes and practices recommended for contributing enhancements to the codebase.

## Overview

- Generally, before developing enhancements to this code base, you should consider [opening an issue](https://github.com/canonical/github-runner-operator/issues) explaining your use case.
- If you would like to chat with us about your use-cases or proposed implementation, you can reach us at [Canonical Charm Development Matrix public channel](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).
- All enhancements require review before being merged. Code review typically examines
  - code quality
  - test coverage

## Code of conduct

When contributing, you must abide by the
[Ubuntu Code of Conduct](https://ubuntu.com/community/ethos/code-of-conduct).

## Changelog

Please ensure that any new feature, fix, or significant change is documented by
adding an entry to the [CHANGELOG.md](docs/changelog.md) file. Use the date of the
contribution as the header for new entries.

To learn more about changelog best practices, visit [Keep a Changelog](https://keepachangelog.com/).

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

### AI

You are free to use any tools you want while preparing your contribution, including
AI, provided that you do so lawfully and ethically.

Avoid using AI to complete issues tagged with the "good first issues" label. The
purpose of these issues is to provide newcomers with opportunities to contribute
to our projects and gain coding skills. Using AI to complete these tasks
undermines their purpose.

We have created instructions and tools that you can provide AI while preparing your contribution: [`copilot-collections`](https://github.com/canonical/copilot-collections)

While it isn't necessary to use `copilot-collections` while preparing your
contribution, these files contain details about our quality standards and
practices that will help the AI avoid common pitfalls when interacting with
our projects. By using these tools, you can avoid longer review times and nitpicks.

If you choose to use AI, please disclose this information to us by indicating
AI usage in the PR description (for instance, marking the checklist item about
AI usage). You don't need to go into explicit details about how and where you used AI.

Avoid submitting contributions that you don't fully understand.
You are responsible for the entire contribution, including the AI-assisted portions.
You must be willing to engage in discussion and respond to any questions, comments,
or suggestions we may have. 

### Signing commits

To improve contribution tracking,
we use the [Canonical contributor license agreement](https://assets.ubuntu.com/v1/ff2478d1-Canonical-HA-CLA-ANY-I_v1.2.pdf)
(CLA) as a legal sign-off, and we require all commits to have verified signatures.

#### Canonical contributor agreement

Canonical welcomes contributions to the GitHub runner Operator. Please check out our
[contributor agreement](https://ubuntu.com/legal/contributors) if you're interested in contributing to the solution.

The CLA sign-off is simple line at the
end of the commit message certifying that you wrote it
or have the right to commit it as an open-source contribution.

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

- `internal/`: Internal Go libraries for the applications
- `cmd/`: Entry points for Go applications (planner, webhook-gateway)
- `charms/`: Entry point for charms (planner, webhook-gateway)

### Style

The applications written in this repository are written in Go.
We like to follow idomatic Go practices and community standards when writing Go code.
We have added an instruction file `go.instructions.md` in `.github/instructions.md` that is used by GitHub Copilot to help you write code that follows these practices.
We have added a [Style Guide](./STYLE.md) that you can refer to for more details.

### Test

This project uses standard Go testing tools for unit tests and integration tests.
You can have a look at the GitHub actions workflows in `.github/workflows/` to see how the tests are run in CI.

Run unit tests using:

```shell
go test -race -v ./...
```

Currently, the internal database package is only covered by integration tests. You can run the database integration tests using:

```shell
POSTGRESQL_DB_CONNECT_STRING="postgres://postgres:password@localhost:5432/postgres?sslmode=disable" go test -cover -tags=integration -v ./internal/database 
```
It assumes you have access to a Postgres server running reachable at $POSTGRESQL_DB_CONNECT_STRING.
You can use `docker` to run a Postgres server locally:
```shell
docker run -d --rm --name postgres -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:16.11
```

Run `webhook-gateway` integration tests using:

```shell
APP_WEBHOOK_SECRET_VALUE=fake APP_PORT=8080 RABBITMQ_CONNECT_STRING="amqp://guest:guest@localhost:5672/" go test -v -cover -tags=integration -race ./cmd/webhook-gateway/...
```

It assumes you have access to a RabbitMQ server running reachable at $RABBITMQ_CONNECT_STRING.
You can use `docker` to run a RabbitMQ server locally:

```shell
docker run -d  --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4-management
```

Run `planner` integration tests using:

```shell
APP_PORT=8080 POSTGRESQL_DB_CONNECT_STRING="postgres://postgres:password@localhost:5432/postgres?sslmode=disable" RABBITMQ_CONNECT_STRING="amqp://guest:guest@localhost:5672/" go test -v -cover -tags=integration -race ./cmd/planner/...
```

It assumes you can reach postgres and rabbitmq servers as described above.

### Test design

We intend to have unit tests for all the logic in the internal packages (located in the `internal/` directory).
Unit tests should test the logic in isolation using mocks/fakes for external dependencies. They should be fast to execute.

Integration tests should test the integration of various components together.
There should be at least an integration test located in the main package of the application they are testing (e.g. in `cmd/webhook-gateway/main_test.go` for the webhook gateway application).

In addition to application integration tests, we also have charm integration tests located in the `charms/tests/integration` directory. These tests should test the charm 
deployment and its integration with other charms. These tests are usually slower than application integration tests, and
should not cover application logic tests; those should be covered in the application integration test.
Aim to focus the charm integration tests only on operational aspects. E.g.

- Testing if the charm deploys correctly
- Testing if the charm config options work as expected
- Testing if the charm integrates correctly with other charms 

Aim to keep all tests (unit, integration, charm integration) 

- Fast to execute
- Reliable
- Deterministic and repeatable
- Easy to set up locally

in order to be able to have fast iterations during development.

### Coverage

We require at least 85% code coverage for all internal packages. New code that lowers the current coverage
should be avoided and discouraged during code reviews.

### Cyclomatic complexity

We recommend keeping cyclomatic complexity of functions/methods below 10.
Higher complexity leads to code that is harder to read, understand, test and maintain.
There are exceptions where higher complexity is justified (e.g., validation, initialization),
but those should require explicit justification using `nolint` directives.

### Charm development

The charm uses the [12 factor app pattern](https://canonical-12-factor-app-support.readthedocs-hosted.com/latest/).
In order to build the `charm-name` rock, use the
`build-charm-name-rock.sh` script.

The respective charm code is in the `charms/charm-name` directory.

Integration tests for the charm are in the `charms/tests/integration` directory.

Have a look at [this tutorial](https://documentation.ubuntu.com/charmcraft/latest/tutorial/kubernetes-charm-go/)
for a step-by-step guide to develop a Kubernetes charm using Go.

To run the charm integration test, the charm file and rock has to be provided as input.
You would need an LXD and MicroK8s cloud to run the tests. Ensure the `microk8s`
controller is active in your Juju client before running the tests. An
example run command in the root directory is as follows:

```shell
tox -e webhook-gateway-integration --  --charm-file ./github-runner-webhook-gateway_amd64.charm --webhook-gateway-image localhost:32000/webhook-gateway:0.1
```

To add the rock to the MicroK8s registry, use the following command:

```shell
rockcraft.skopeo copy \
  --insecure-policy --dest-tls-verify=false \
  oci-archive:webhook-gateway_0.1_amd64.rock \
  docker://localhost:32000/webhook-gateway:0.1
```
