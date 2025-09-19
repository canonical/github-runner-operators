# Contribute

## Overview

This document explains the processes and practices recommended for contributing enhancements to the codebase.

* Generally, before developing enhancements to this code base, you should consider [opening an issue](https://github.com/canonical/github-runner-operator/issues) explaining your use case.
* If you would like to chat with us about your use-cases or proposed implementation, you can reach us at [Canonical Charm Development Matrix public channel](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).
* All enhancements require review before being merged. Code review typically examines
    * code quality
    * test coverage

## Develop

For any problems with this charm, please [report bugs here](https://github.com/canonical/github-runner-operator/issues).

The code can be downloaded as follows:

```shell
git clone https://github.com/canonical/github-runner-operators.git
```

The code structure is as follows

- `internal/`: Internal libraries for the applications
- `webhook-gateway`: The webhook gateway application code


### Test

This project uses standard Go testing tools for unit tests and integration tests.
You can have a look at the GitHub actions workflows in `.github/workflows/` to see how the tests are run in CI.

Run unit tests using:

```shell
go test -race -v ./...
```

Run `webhook-gateway` integration tests using:

```shell
APP_PORT=8080 WEBHOOK_SECRET=fake RABBITMQ_CONNECT_STRING="amqp://guest:guest@localhost:5672/" go test -cover -v  ./webhook-gateway -integratio
```

It assumes you have access to a RabbitMQ server running reachable at $RABBITMQ_CONNECT_STRING.
You can use `docker` to run a RabbitMQ server locally:

```shell
docker run -d  --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4-management
```

## Canonical contributor agreement

Canonical welcomes contributions to this repository. Please check out our [contributor agreement](https://ubuntu.com/legal/contributors) if you’re interested in contributing to the solution.