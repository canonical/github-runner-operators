GitHub runner operators
=======================

GitHub runner operators are a set of Juju charms that operate self-hosted
GitHub Actions runners. The product receives GitHub webhooks, routes job events
through a message broker, and exposes a planner API that coordinates runner
capacity and job lifecycle data.

This repository ships two primary charms:

- GitHub runner webhook gateway: a web service that validates GitHub webhook signatures and forwards workflow job events to an AMQP-compatible message broker.
- GitHub runner planner: a REST API service that consumes workflow job events, records job state in PostgreSQL, and manages runner flavors and auth tokens for downstream runner integrations.

This product is intended for platform engineers, site reliability engineers, and GitHub organization
administrators who need reliable, observable, and policy-driven control of
self-hosted runners at scale.

The project has the following core dependencies and integrations:

- AMQP message broker: required by both charms for moving webhook events from the gateway to the planner. RabbitMQ is the expected broker.
- PostgreSQL: required by the planner to persist job and flavor data.
- Tracing and metrics: both charms can emit OpenTelemetry data and Prometheus metrics so that Grafana dashboards and tracing backends can be used for observability.
- `GitHub runner charm <https://github.com/canonical/github-runner-operator>`_: consumes the planner relation to retrieve auth tokens and desired flavor configuration.

GitHub sends workflow job webhooks to the webhook gateway. The gateway validates
and forwards events to the broker. The planner consumes those events, stores job
state, and exposes APIs and relations that allow the GitHub runner charm to
provision the right runners for each job.


In this documentation
---------------------

.. grid:: 1 1 2 2

    .. grid-item-card:: Tutorial
        :link: /tutorial/index
        :link-type: doc

        **Get started** - use webhook gateway and planner charms.

    .. grid-item-card:: How-to guides
        :link: /how-to/index
        :link-type: doc

        **Step-by-step guides** - learn key operations and customization.

.. grid:: 1 1 2 2

    .. grid-item-card:: Reference
        :link: /reference/index
        :link-type: doc

        **Technical information** - review the topics relevant to GitHub Runner Operators.

    .. grid-item-card:: Explanation
        :link: /explanation/index
        :link-type: doc

        **Concepts** - understand the design and architecture of the GitHub Runner Operators.

.. toctree::
    :hidden:
    :maxdepth: 2

    Tutorials <tutorial/index>
    How-to guides <how-to/index>
    Reference <reference/index>
    Explanation <explanation/index>
    Changelog <changelog>
