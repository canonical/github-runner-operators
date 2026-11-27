---
myst:
  html_meta:
    "description lang=en": "Put GARM behind HAProxy with TLS termination and restrict its metrics endpoint."
---

(how_to_garm_haproxy_tls)=

# Put GARM behind HAProxy with TLS termination

GARM serves its API and Prometheus metrics on port 8080. The GARM workload does
not terminate TLS. This guide puts the workload behind the HAProxy charm,
terminates client TLS at HAProxy, and keeps the metrics endpoint off the public
route.

The guide uses ``ingress-configurator`` as the adapter between GARM's
``ingress`` relation and HAProxy's ``haproxy-route`` relation. It is also the
place where the ``/metrics`` deny rule is configured.

## Understand the deployment

The GARM charm runs on Kubernetes, while the HAProxy charm is a machine charm.
Use two Juju models when the charms run on their normal substrates:

- **Kubernetes model:** ``garm``, ``postgresql-k8s``, and one or more
  ``garm-configurator`` applications.
- **Machine model:** ``haproxy``, ``ingress-configurator``, and a certificate
  provider.

Offer ``ingress-configurator:ingress`` from the machine model and consume it in
the Kubernetes model. The adapter and HAProxy stay in the same model, so the
``haproxy-route`` relation remains local to the proxy model.

```{mermaid}
flowchart LR
    R[Runner VMs and GitHub] -->|HTTPS :443| H["HAProxy<br/>TLS termination"]
    H --> IC["ingress-configurator<br/>route adapter"]
    IC -->|cross-model ingress| G["garm<br/>API and callbacks :8080"]
    G --> PG[(postgresql-k8s)]
    IC -. deny /metrics .- M["Monitoring<br/>via private metrics relation"]
```

The certificate provider is either:

- ``self-signed-certificates`` for development or an isolated test
  environment; or
- ``manual-tls-certificates`` (or another provider implementing
  ``tls-certificates``) for a certificate signed by the required CA.

For production, use a certificate whose CA is trusted by GitHub and by the
runner image. A self-signed certificate also requires the CA to be trusted by
the runner VMs before they can call GARM.

## Prepare the models

This guide assumes that GARM and PostgreSQL are already deployed and that the
GARM configurator is integrated with GARM. Follow the
{ref}`GARM deployment tutorial <tutorial_garm>` first if they are not.

You also need:

- a DNS name, such as ``garm.example.com``, that resolves to the HAProxy
  address;
- network access from GitHub and the runner VMs to HAProxy on TCP port 443;
- permission to create a cross-model relation between the two models; and
- a monitoring system in the Kubernetes model if metrics are required.

Create or select a machine model for HAProxy and switch to it for the next
commands:

```bash
juju add-model garm-ingress
juju switch garm-ingress
```

The Kubernetes model is called ``garm`` in the examples below. Replace model
and controller names with those used by your deployment.

## Deploy HAProxy and the route adapter

Deploy HAProxy, a certificate provider, and the adapter in the machine model:

```bash
juju deploy haproxy --channel=3.2/edge --base=ubuntu@26.04
juju deploy ingress-configurator --channel=edge
juju deploy self-signed-certificates cert

juju integrate haproxy:certificates cert:certificates
juju integrate ingress-configurator:haproxy-route haproxy:haproxy-route
```

For a production certificate, replace ``self-signed-certificates`` with
``manual-tls-certificates``:

```bash
juju remove-application cert --force
juju deploy manual-tls-certificates cert
juju integrate haproxy:certificates cert:certificates
```

Use the manual certificate charm's actions to sign and provide HAProxy's CSR.
Do not relate two certificate providers to the same HAProxy application.

Set the public hostname and deny the metrics path:

```bash
juju config haproxy external-hostname=garm.example.com
juju config ingress-configurator \
  hostname=garm.example.com \
  deny-paths=/metrics
```

The route adapter forwards the remaining GARM paths, including the metadata,
callback, webhook, and agent paths. ``deny-paths`` prevents the adapter from
routing ``/metrics`` to GARM. Do not expose GARM's port 8080 directly.

## Connect the GARM model

Offer the adapter's ingress endpoint from the machine model:

```bash
juju offer ingress-configurator:ingress garm-ingress
juju show-offer garm-ingress
```

The last command shows the offer URL. Switch to the Kubernetes model and
consume it:

```bash
juju switch <garm-controller>:garm
juju consume <controller>:<user>/garm-ingress.garm-ingress garm-ingress
juju integrate garm:ingress garm-ingress:ingress
```

Use the exact offer URL printed by ``juju show-offer``.

Wait for the relation and certificate provider to settle:

```bash
juju status --watch 5s
```

The GARM application can use its in-cluster service URL while the ingress
relation is absent or not ready. That fallback is HTTP and is not reachable by
runner VMs outside the Kubernetes cluster. Do not treat that fallback as the
production endpoint. Once the relation supplies an external URL, the charm
reconciles GARM's controller URLs again.

## Keep metrics private

GARM's API and metrics share port 8080. There is no separate GARM metrics port
to expose through HAProxy. Keep the public route configured with
``deny-paths=/metrics`` and scrape metrics through the GARM
``metrics-endpoint`` relation from Prometheus or COS in the Kubernetes model.

For example, integrate GARM with the monitoring stack used by the deployment:

```bash
juju integrate garm prometheus-k8s
```

The exact monitoring application and relation name depend on the monitoring
stack. The important properties are:

- the monitoring system can reach the private Kubernetes service;
- TCP port 8080 is not exposed to the Internet; and
- no public HAProxy route sends ``/metrics`` to GARM.

If an external monitoring system must scrape metrics, give it a separate,
network-restricted path or hostname. Do not remove the deny rule from the
runner and GitHub endpoint.

## Verify the TLS endpoint

Find the HAProxy address in the machine model and test the public hostname.
For a self-signed certificate, use the CA certificate from the certificate
provider or use ``--insecure`` only for a test:

```bash
juju switch garm-ingress
HAPROXY_IP=$(juju status --format=json | \
  jq -r '.applications.haproxy.units | to_entries[0].value."public-address"')

curl --resolve garm.example.com:443:${HAPROXY_IP} \
  --insecure https://garm.example.com/api/v1/metadata
```

A response from the GARM API confirms that HAProxy is routing the request.
The ``/metrics`` request must not return GARM's Prometheus exposition:

```bash
curl --resolve garm.example.com:443:${HAPROXY_IP} \
  --insecure -i https://garm.example.com/metrics
```

Inspect the route adapter and HAProxy endpoints if either request is
unexpected:

```bash
juju run ingress-configurator/leader get-proxied-endpoints
juju run haproxy/leader get-proxied-endpoints
```

Finally, verify the controller URLs from the authenticated GARM API. The
following request is normally run from a network that can reach the GARM
service; obtain credentials with the
{ref}`GARM credentials action <how_to_retrieve_garm_credentials>`:

```bash
curl -sS -u '<username>:<password>' \
  http://<garm-service-address>:8080/api/v1/controller \
  | jq '{metadata_url, callback_url, webhook_url, agent_url, allow_insecure_garm_agent}'
```

After the HAProxy relation is ready, the output should show:

- ``metadata_url``, ``callback_url``, ``webhook_url``, and ``agent_url`` using
  ``https://garm.example.com``; and
- ``allow_insecure_garm_agent`` set to ``false``.

The agent URL is especially important: GARM agents use it for their callback
connection, and the agent's remote shell is disabled when the effective URL is
plain HTTP.

## Handle self-signed certificates

With ``self-signed-certificates``, the certificate is valid only when the
client trusts the generated CA. Install that CA in the runner image and ensure
GARM's runner configuration includes the CA bundle required by the GARM agent.
Otherwise the runner can resolve the public URL but will fail its TLS
handshake. Prefer a CA already trusted by the runner image for production.
