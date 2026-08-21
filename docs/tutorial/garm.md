---
myst:
  html_meta:
    "description lang=en": "A step-by-step tutorial for deploying the GARM charm for the first time."
---

(tutorial_garm)=

# Deploy the GARM charm for the first time

GARM (GitHub Actions Runner Manager) deploys and manages self-hosted GitHub Actions runners. The
GARM charm runs GARM on Kubernetes, backed by PostgreSQL, and takes its runner configuration from
the GARM configurator charm.

In this tutorial you'll deploy GARM, connect it to a repository of your own through a GitHub App, and
watch it register a runner scale set with GitHub.

Runners themselves are created on an OpenStack cloud. Setting up an OpenStack cloud, and building a
runner image for it, is a substantial task in its own right, so this tutorial uses placeholder
OpenStack values and a stand-in image provider. Everything up to and including the scale set
registration on GitHub is real: the last section explains exactly which values you would change to
make runners boot.

## What you'll do

1. Deploy GARM and PostgreSQL, and integrate them.
1. Deploy a stand-in image provider.
1. Deploy the GARM configurator and configure a scale set.
1. Integrate the configurator with GARM and the image provider.
1. Verify that the scale set is registered with GitHub.
1. Clean up the environment.

## What you'll need

- A workstation, such as a laptop, with an AMD64 architecture, at least 4 CPU cores, 8 GB of
  RAM, and 50 GB of disk space.
- A GitHub repository that you administer. The tutorial registers a runner scale set on it. A
  scratch repository is a good choice.
- Permission to create a GitHub App in your account or organization.

You do *not* need an OpenStack cloud for this tutorial.

```{tip}
You can use Multipass to create an isolated environment:

    multipass launch 24.04 --name garm-tutorial-vm --cpus 4 --memory 8G --disk 50G
    multipass shell garm-tutorial-vm
```

### Install Juju and MicroK8s

This tutorial requires Juju 3 and MicroK8s. Use
[Concierge](https://github.com/canonical/concierge) to install and configure both:

```bash
sudo snap install --classic concierge
sudo concierge prepare -p microk8s
```

Concierge also bootstraps a Juju controller on MicroK8s. Verify it with:

```bash
juju controllers
```

If Concierge did not bootstrap a controller, run:

```bash
juju bootstrap microk8s tutorial-controller
```

The verification step at the end of this tutorial also uses `curl` and `jq`.
Install them using:

```bash
sudo apt install -y curl jq
```

### Create a GitHub App

GARM authenticates to GitHub as a GitHub App. Create one at
[https://github.com/settings/apps/new](https://github.com/settings/apps/new):

1. Give the app a name, and enter any URL as the homepage URL.
1. Under **Webhook**, clear the **Active** checkbox. Scale sets poll GitHub for jobs, so GARM does
   not need to receive webhooks.
1. Under **Permissions > Repository permissions**, grant:
   - **Actions**: Read and write
   - **Administration**: Read and write
1. Create the app, then select **Generate a private key** and save the downloaded `.pem` file in
   your home directory.

Note the **App ID** shown at the top of the app's settings page.

Finally, select **Install App** and install it on the repository you want to add runners to. After
installing, the browser URL ends in the installation ID:
`https://github.com/settings/installations/<installation-id>`. Note that number as well.

```{important}
Save the private key somewhere under your home directory. Juju is a strictly confined snap and
cannot read files in `/tmp`.
```

## Set up the environment

Create a model to keep this tutorial's workload separate from your other work:

```bash
juju add-model garm-tutorial
```

## Deploy GARM and PostgreSQL

GARM stores its state in PostgreSQL, so deploy both and integrate them:

```bash
juju deploy garm --channel latest/edge
juju deploy postgresql-k8s --channel 16/stable --trust
juju integrate garm postgresql-k8s
```

GARM reports `missing integrations: postgresql` until PostgreSQL finishes bootstrapping and hands
over its credentials, which takes a few minutes. Watch the deployment settle with
`juju status --watch 5s`. GARM then moves on to waiting for the scale set configuration, which the
next steps supply:

```{terminal}
:output-only:

App             Version  Status   Scale  Charm           Channel      Rev  Address         Exposed  Message
garm                     waiting      1  garm            latest/edge   94  10.152.183.171  no       Waiting for garm-configurator relation
postgresql-k8s  16.14    active       1  postgresql-k8s  16/stable    927  10.152.183.178  no

Unit               Workload  Agent  Address     Ports  Message
garm/0*            waiting   idle   10.1.22.21         Waiting for garm-configurator relation
postgresql-k8s/0*  active    idle   10.1.22.15         Primary
```

## Deploy a stand-in image provider

Runners boot from an OpenStack image, and the GARM configurator requires an integration with a
charm that supplies the image ID over the `github_runner_image_v0` interface. Because this tutorial
does not create real runners, you can satisfy that requirement with
[`any-charm`](https://charmhub.io/any-charm), a charm whose behavior you supply as source code.

Write a small charm that publishes a placeholder image ID whenever something integrates with it:

```bash
cat > fake_image_builder.py <<'EOF'
from any_charm_base import AnyCharmBase

IMAGE_ID = "00000000-0000-0000-0000-000000000000"
IMAGE_TAGS = "x64,noble"


class AnyCharm(AnyCharmBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.framework.observe(
            self.on["provide-github-runner-image-v0"].relation_joined,
            self._on_image_relation_joined,
        )

    def _on_image_relation_joined(self, event):
        event.relation.data[self.unit]["id"] = IMAGE_ID
        event.relation.data[self.unit]["tags"] = IMAGE_TAGS
EOF
```

Deploy the charm as `fake-image-builder`, passing that file as the charm's source:

```bash
juju deploy any-charm fake-image-builder --channel latest/beta \
  --config src-overwrite="$(python3 -c 'import json; print(json.dumps({"any_charm.py": open("fake_image_builder.py").read()}))')"
```

## Configure a scale set

The GARM configurator charm holds the configuration for a single scale set: which repository it
serves, how many runners it may create, and the OpenStack project the runners live in. GARM reads
that configuration over an integration and creates the scale set.

Deploy the configurator:

```bash
juju deploy garm-configurator --channel latest/edge
```

The OpenStack password and the GitHub App private key are passed as Juju secrets rather than plain
configuration. Create them, replacing the path with your own private key:

```bash
juju add-secret openstack-password value=placeholder-password
juju add-secret github-app-private-key value#file=$HOME/your-app.private-key.pem
```

Each command prints a secret URI, such as `secret:8rdhlq3nsgh46i3tnpbg`. Grant both secrets to the
configurator so it can read them:

```bash
juju grant-secret openstack-password garm-configurator
juju grant-secret github-app-private-key garm-configurator
```

Now configure the charm. Enter the `openstack-*` values exactly as they appear below: they are
placeholders, stored and forwarded but never used to contact a cloud in this tutorial. Replace
every value written in angle brackets with your own — the two secret URIs printed above, the app ID
and installation ID you noted earlier, and your repository:

```bash
juju config garm-configurator \
  openstack-auth-url="https://keystone.example.com:5000/v3" \
  openstack-username="tutorial-user" \
  openstack-password="<openstack-password-secret-uri>" \
  openstack-project-name="tutorial-project" \
  openstack-user-domain-name="Default" \
  openstack-project-domain-name="Default" \
  openstack-region-name="RegionOne" \
  openstack-network="external-net" \
  github-app-id=<app-id> \
  github-app-installation-id=<installation-id> \
  github-app-private-key="<private-key-secret-uri>" \
  name="tutorial-scaleset" \
  flavor="m1.large" \
  os-arch="amd64" \
  min-idle-runner=0 \
  max-runner=1 \
  labels="tutorial" \
  repo="<your-user>/<your-repo>"
```

`min-idle-runner=0` keeps GARM from trying to create a runner while it has nowhere to create one.

The configurator now reports that it is waiting for an image provider
in the output of `juju status`:

```{terminal}
:output-only:

Unit                  Workload  Agent  Address     Ports  Message
garm-configurator/0*  waiting   idle   10.1.22.28         Waiting for image builder relation
```

## Integrate the charms

Connect the configurator to the image provider and to GARM:

```bash
juju integrate garm-configurator:image fake-image-builder:provide-github-runner-image-v0
juju integrate garm garm-configurator
```

Over the first relation, `fake-image-builder` publishes its image ID to the configurator, which
becomes active. Over the second relation, the configurator hands GARM the scale set configuration, and GARM
registers the repository and the scale set with GitHub.

Run `juju status` to check the result:

```{terminal}
:output-only:

App                 Version  Status  Scale  Charm              Channel      Rev  Address         Exposed  Message
fake-image-builder           active      1  any-charm          latest/beta  175  10.152.183.31   no
garm                         active      1  garm               latest/edge   94  10.152.183.171  no
garm-configurator            active      1  garm-configurator  latest/edge   86  10.152.183.68   no       Ready
postgresql-k8s      16.14    active      1  postgresql-k8s     16/stable    927  10.152.183.178  no

Unit                   Workload  Agent  Address     Ports  Message
fake-image-builder/0*  active    idle   10.1.22.55
garm-configurator/0*   active    idle   10.1.22.47         Ready
garm/0*                active    idle   10.1.22.21
postgresql-k8s/0*      active    idle   10.1.22.15         Primary
```

An active GARM unit means the whole reconciliation succeeded, including the calls to GitHub. If
GARM reports `GARM sync failed` instead, its GitHub credentials were rejected — see
[Troubleshooting](#troubleshooting) for possible reasons.

## Verify the scale set

Open your repository on GitHub and go to **Settings > Actions > Runners**. `tutorial-scaleset` is
listed there as a runner scale set. GARM created it through the GitHub Actions API using your
GitHub App.

You can also ask GARM directly. Retrieve its admin credentials:

```bash
juju run garm/0 get-credentials
```

Then log in to the GARM API and list the scale sets:

```bash
GARM_URL="http://$(juju status --format=json | jq -r '.applications.garm.address'):8080/api/v1"
TOKEN=$(curl -sS -X POST "$GARM_URL/auth/login" \
  -d '{"username": "admin", "password": "<password-from-the-action>"}' | jq -r .token)
curl -sS "$GARM_URL/scalesets" -H "Authorization: Bearer $TOKEN" \
  | jq '.[] | {name, repo_name, max_runners, image}'
```

This command should return:

```{terminal}
:output-only:

{
  "name": "tutorial-scaleset",
  "repo_name": "your-user/your-repo",
  "max_runners": 1,
  "image": "00000000-0000-0000-0000-000000000000"
}
```

The `image` field holds the placeholder ID published by the stand-in image provider, which is where
a real image ID would appear.

Congratulations! You have a working GARM deployment with a scale set registered on GitHub.

## What changes with a real OpenStack cloud

At this point every part of the deployment is real except the runners. GARM registers the scale set
under its own name and under the configured labels, so a workflow job that sets either
`runs-on: tutorial-scaleset` or `runs-on: tutorial` is assigned to it. GARM picks the job up over
its connection to GitHub and asks OpenStack for a runner, which fails against the placeholder
credentials — `juju debug-log --include garm/0` shows the failure. Three things stand between this
deployment and one that runs jobs:

- **Real OpenStack credentials.** The eight `openstack-*` options take the values of an existing
  project. No other configuration changes are required.
- **A runner image.** `fake-image-builder` stands in for a charm that builds a runner image in your
  OpenStack project and publishes its ID. Replace it with a real image provider and remove the
  stand-in.
- **A reachable GARM.** Runners call back to GARM to report their status, using a URL that GARM
  derives from its own address. The in-cluster address used in this tutorial is not reachable from
  an OpenStack tenant, so GARM needs an ingress with an address that the runner network can reach.

(troubleshooting)=

## Troubleshooting

**GARM reports `GARM sync failed`.** GARM could not complete a call to GitHub. The usual causes are
a wrong app ID or installation ID, a private key that does not belong to the app, or a GitHub App
that lacks the Actions and Administration permissions. Check the details with
`juju debug-log --include garm/0`.

**`juju add-secret` reports that the private key file does not exist.** Juju cannot read files
under `/tmp`. Move the key into your home directory and pass that path.

**The configurator stays blocked on `Missing required configuration`.** The status message names
the first option that is missing. Every option in the `juju config` command above is required
except `labels`.

## Clean up the environment

Remove everything this tutorial created by destroying the model:

```bash
juju destroy-model garm-tutorial --destroy-storage
```

The scale set registered on GitHub is removed along with GARM. If it is still listed under
**Settings > Actions > Runners** afterwards, you can delete it from that page.

For a full teardown of Juju and MicroK8s, see
[Tear down your test environment](https://canonical.com/juju/docs/juju-cli/3.6/howto/manage-your-juju-deployment/tear-down-your-juju-deployment-local-testing-and-development/).

## Next steps

- [Retrieve GARM admin credentials](../how-to/retrieve-garm-credentials.md) to use the GARM API or
  `garm-cli`.
- [Enable log forwarding](../how-to/enable-log-forwarding.md) to send GARM logs to a log
  aggregator.
- Learn more about the available [relation endpoints](../reference/charms.md) for the charms.
