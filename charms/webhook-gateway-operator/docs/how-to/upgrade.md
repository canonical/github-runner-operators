<!--
    Remember to update this file for your charm!!
    If applicable, use this placeholder to provide information on how to
    upgrade the charm. Some questions to answer:
    * Should we suggest that the user back up the charm or its database
      before upgrading?
    * Does the user need to reset any configurations?
-->

# How to upgrade

To upgrade the webhook gateway charm, use the [`juju refresh`](https://documentation.ubuntu.com/juju/3.6/reference/juju-cli/list-of-juju-cli-commands/refresh/) command.

## Before you begin

Before performing an upgrade, ensure that your Juju model is in a healthy state:

```bash
juju status
```

Confirm that all units are active and idle.

## Refresh to the latest revision

To upgrade webhook gateway to the latest revision from Charmhub:

```bash
juju refresh github-runner-webhook-gateway
```

This command will pull and apply the most recent revision of the webhook gateway charm from the same channel it was originally deployed from.

## Verify the upgrade

After the refresh completes, confirm that the charm and its units are active:

```bash
juju status github-runner-webhook-gateway
```

The application status should display as:

```
Active   github-runner-webhook-gateway/0  ...
```
