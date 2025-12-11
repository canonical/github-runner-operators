<!--
Copyright 2025 Canonical Ltd.
See LICENSE file for licensing details.
-->

# How to upgrade

To upgrade the planner charm, use the [`juju refresh`](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/refresh/) command.

## Before you begin

Before performing an upgrade, ensure that:

- You have followed the [PostgreSQL charm documentation](https://canonical-charmed-postgresql-k8s.readthedocs-hosted.com/14/how-to/back-up-and-restore/create-a-backup/) to back up your database.

- Your Juju model is in a healthy state:

```bash
juju status
```

Confirm that all units are active and idle.

## Refresh to the latest revision

Upgrade the planner charm to the latest revision from Charmhub:

```bash
juju refresh github-runner-planner
```

This command will pull and apply the most recent revision of the planner charm from the same channel it was originally deployed from.

## Verify the upgrade

After the refresh completes, confirm that the charm and its units are active:

```bash
juju status github-runner-planner
```

The application status should display as:

```
Active   github-runner-planner/0  ...
```
