---
myst:
  html_meta:
    "description lang=en": "How to configure the GARM configurator to use the LXD provider with virtual machine runners."
---

(how_to_configure_lxd_provider)=

# How to configure the LXD provider

Use this guide to configure a ``garm-configurator`` application to create
runners with the GARM LXD provider. GARM runs on Kubernetes and connects to an
external LXD server over HTTPS using mutual TLS. In this revision, LXD runners
are virtual machines only.

```{note}
LXD virtual machine runners require LXD 6.7 or later. The LXD provider uses the
``boot.mode`` instance option, which LXD added for virtual machines in that
release. LXD 5.21 and earlier fail with
``"boot.mode" isn't supported for "virtual-machine"``.
```

## What you'll need

- A ``garm`` application deployed with PostgreSQL, and a ``garm-configurator``
  application. See the {ref}`deployment tutorial <tutorial_garm>`.
- An LXD server running 6.7 or later, reachable over HTTPS from the Kubernetes
  cluster that runs GARM.
- An existing LXD project and profile for the runners. The built-in ``default``
  project and ``default`` profile are sufficient to start.
- A GitHub App ID, installation ID, and private key. The GitHub App must be
  installed on the organization or repository that will own the scale set.
- Permission to change Juju configuration and create Juju secrets.

## Enable the LXD HTTPS API

The provider connects to the LXD API over HTTPS. Enable it on the LXD server:

```bash
lxc config set core.https_address :8443
```

Confirm the project and profile exist. Replace ``default`` with the project you
want to use:

```bash
lxc project list
lxc profile list --project default
```

If you use a custom profile, create it before configuring the charm. The
``flavor`` option later refers to this profile by name. For example:

```bash
lxc profile copy default garm-runner --project default
```

## Generate and trust a client certificate

Generate a client certificate and key for GARM:

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout client.key -out client.crt \
  -subj "/CN=garm-configurator" \
  -addext "extendedKeyUsage=clientAuth"
```

Add the certificate to the LXD trust store:

```bash
lxc config trust add --name garm-configurator client.crt
```

The certificate must be trusted before GARM can create instances. LXD
authenticates the client certificate; it does not require the certificate to be
signed by a public CA.

## Get the LXD server certificate

If the LXD server certificate is not signed by a public CA, GARM needs the
server certificate to pin it. The example uses ``jq`` to parse the LXD API
response. Save the certificate:

```bash
lxc query /1.0 | jq -r '.environment.certificate' > server.crt
```

If the LXD server certificate is signed by a public CA, you can skip this step
and leave the ``lxd-server-certificate`` option unset.

## Create the Juju secrets

The client certificate, client key, LXD server certificate, and GitHub App
private key are passed as Juju secrets. Create them and grant them to the
configurator. Capture the secret URIs printed by ``juju add-secret``. Replace
``github-app.pem`` with the path to your GitHub App private key:

```bash
CERT=$(juju add-secret garm-lxd-client-cert value="$(cat client.crt)" | tail -1)
KEY=$(juju add-secret garm-lxd-client-key value="$(cat client.key)" | tail -1)
SRV=$(juju add-secret garm-lxd-server-cert value="$(cat server.crt)" | tail -1)
GHKEY=$(juju add-secret garm-github-app-key value="$(cat github-app.pem)" | tail -1)

for secret in "$CERT" "$KEY" "$SRV" "$GHKEY"; do
  juju grant-secret "$secret" garm-configurator
done
```

Skip ``SRV`` when the LXD server certificate is publicly trusted.

## Configure the configurator

Set the LXD provider options and the scale set fields. The following example
creates an organization-level scale set. Use ``repo`` instead of ``org`` for a
repository-level scale set:

```bash
juju config garm-configurator \
  provider-type=lxd \
  lxd-api-url=https://lxd.example.com:8443 \
  lxd-project-name=default \
  lxd-secure-boot=false \
  lxd-client-certificate="$CERT" \
  lxd-client-key="$KEY" \
  lxd-server-certificate="$SRV" \
  github-app-id="<app-id>" \
  github-app-installation-id="<installation-id>" \
  github-app-private-key="$GHKEY" \
  name=garm-lxd-runners \
  flavor=default \
  os-arch=amd64 \
  image=ubuntu:24.04 \
  min-idle-runner=1 \
  max-runner=5 \
  labels=lxd,ubuntu \
  org="<organization>"
```

If you skipped the server certificate, omit the ``lxd-server-certificate`` line.

The options specific to LXD are:

- ``lxd-api-url``: the LXD HTTPS API URL, for example
  ``https://lxd.example.com:8443``.
- ``lxd-project-name``: an existing project. Defaults to ``default``.
- ``lxd-secure-boot``: whether the virtual machines use secure boot.
- ``lxd-client-certificate`` and ``lxd-client-key``: Juju secrets containing
  the trusted client certificate and key.
- ``lxd-server-certificate``: an optional Juju secret containing the LXD server
  certificate for certificate pinning.

The scale set options also apply:

- ``flavor`` is the name of an existing LXD profile in the project. Use
  ``default`` for the built-in profile.
- ``image`` is an LXD image reference: ``ubuntu:24.04`` from the default
  ``ubuntu`` simplestreams remote, a local image alias, or an image fingerprint.
- ``os-arch`` must match the image architecture, for example ``amd64``.
- ``min-idle-runner`` and ``max-runner`` control the number of runners.

## Integrate the configurator with GARM

```bash
juju integrate garm garm-configurator
```

GARM reads the relation data, creates the LXD provider, and creates the scale
set. The configurator remains active when the configuration is valid.

## Verify the deployment

Check the application status:

```bash
juju status
```

Wait until both ``garm`` and ``garm-configurator`` are active. Then check the
LXD project for the runner instances:

```bash
lxc list --project default
```

Runner instances created by the provider are ``VIRTUAL-MACHINE`` instances and
use the profile named by ``flavor``. The provider tags them with GARM metadata
such as ``user.runner-controller-id`` and ``user.runner-pool-id``.

## Troubleshooting

- ``"boot.mode" isn't supported for "virtual-machine"``: the LXD server is
  older than 6.7. Upgrade LXD before using virtual machine runners.
- ``looking for profile <name>``: the ``flavor`` profile does not exist in the
  configured project. Create the profile or set ``flavor=default``.
- ``x509: certificate signed by unknown authority``: provide the LXD server
  certificate with ``lxd-server-certificate``, or use a server certificate
  signed by a public CA.
- The provider is not created or the scale set is missing: check that the
  client certificate and key secrets were granted to ``garm-configurator`` and
  that ``provider-type=lxd`` is set.
- Runners start but do not register with GitHub: the runner must reach GARM's
  callback and metadata URLs. Use an ingress address reachable from the LXD
  network, as for the OpenStack provider.

## Security notes

- Treat the client key and the GitHub App private key as sensitive. Store them
  in Juju secrets and grant them only to the configurator.
- Use secure boot (``lxd-secure-boot=true``) when the runner image supports it.
- Restrict access to the LXD API and the GARM ingress to the networks that need
  them.
