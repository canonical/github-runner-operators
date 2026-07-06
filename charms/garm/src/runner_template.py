# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Render runner-behaviour options into a GARM runner-install template.

GARM 0.2 stores the runner-install script as a server-side template that a
scaleset references by ``template_id``. The six operator-facing runner options
(docker mirror, proxy/aproxy, telemetry, pre-job hook) are delivered by copying
GARM's system ``github_linux`` template and injecting two blocks right after the
shebang — before the base template's ``set -e`` — so a best-effort step can never
abort the whole bootstrap:

  * a *pre-install* block that runs as root before the runner is installed
    (aproxy, docker registry mirror, static host prep), and
  * a *runner job hooks* block that writes the GitHub job-start hook and the
    runner ``env`` file under ``/home/runner/actions-runner`` (GARM hardcodes the
    ``runner`` user and that path).

Both blocks are ported line-for-line from the production
``canonical/github-runner-operator`` templates (``openstack-userdata.sh.j2``,
``env.j2``, ``pre-job.j2``) so the runner behaves identically to the previous
machine-charm implementation.

The reconciler creates/updates the per-scaleset template with the bytes returned
by :func:`build_template_data` and only does so when :meth:`RunnerConfig.has_config`
is true.
"""

import ipaddress
import json
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass

_PORT_TOKEN_RE = re.compile(r"^\d{1,5}(-\d{1,5})?$")

# GARM hardcodes the runner username and actions-runner directory; the env file
# read by the runner service therefore lives at the path below.
RUNNER_USER = "runner"
RUNNER_HOME = "/home/runner/actions-runner"
PRE_JOB_HOOK_PATH = f"{RUNNER_HOME}/pre-job.sh"
RUNNER_ENV_PATH = f"{RUNNER_HOME}/env"

# Databag keys written by the garm-configurator charm. Kept here as the single
# source of truth for the configurator→garm relation contract for runner options.
DATABAG_KEYS = (
    "dockerhub_mirror",
    "runner_http_proxy",
    "aproxy_exclude_addresses",
    "aproxy_redirect_ports",
    "otel_collector_endpoint",
    "pre_job_script",
)


@dataclass(frozen=True)
class RunnerConfig:
    """Runner-behaviour options sourced from the garm-configurator relation.

    Every field is a plain string; an empty string means "unset". Values are
    validated upstream by the configurator charm, so rendering here is purely
    mechanical.

    Attributes:
        dockerhub_mirror: Docker registry mirror URL, or "".
        runner_http_proxy: Upstream HTTP proxy that aproxy forwards to, or "".
        aproxy_exclude_addresses: Comma-separated addresses/CIDRs to bypass, or "".
        aproxy_redirect_ports: Comma-separated ports / N-M ranges to redirect, or "".
        otel_collector_endpoint: OTEL exporter endpoint, or "".
        pre_job_script: Operator bash appended to the pre-job hook, or "".
    """

    dockerhub_mirror: str = ""
    runner_http_proxy: str = ""
    aproxy_exclude_addresses: str = ""
    aproxy_redirect_ports: str = ""
    otel_collector_endpoint: str = ""
    pre_job_script: str = ""

    @classmethod
    def from_databag(cls, data: Mapping[str, str]) -> "RunnerConfig":
        """Build a config from a relation databag, ignoring missing keys.

        Args:
            data: The relation unit databag (or any mapping).

        Returns:
            A RunnerConfig with each field taken from its databag key, "" if absent.
        """
        return cls(**{key: (data.get(key) or "").strip() for key in DATABAG_KEYS})

    def has_config(self) -> bool:
        """Whether any runner option is set (i.e. a custom template is needed).

        Returns:
            True if at least one field is non-empty.
        """
        return any(getattr(self, key) for key in DATABAG_KEYS)


def build_template_data(base: bytes, config: RunnerConfig) -> bytes:
    """Inject the runner-option blocks into a base runner-install template.

    The blocks are inserted immediately after the shebang line (before the base
    template's ``set -e``), mirroring GARM's documented "prepend after the
    shebang" approach.

    Args:
        base: The system ``github_linux`` template bytes to copy from.
        config: The runner options to render.

    Returns:
        The new template bytes, with the pre-install and job-hook blocks injected.
    """
    text = base.decode("utf-8")
    injection = render_pre_install(config) + render_pre_job_hooks(config)
    if "\n" in text:
        shebang, rest = text.split("\n", 1)
        return f"{shebang}\n{injection}{rest}".encode("utf-8")
    return f"{text}\n{injection}".encode("utf-8")


def render_pre_install(config: RunnerConfig) -> str:
    """Render the root pre-install block (runs before the runner is installed).

    Args:
        config: The runner options to render.

    Returns:
        A bash snippet, terminated by a newline.
    """
    sections = ["", "# ===== charm-injected pre-install setup (runs as root) ====="]
    if config.runner_http_proxy:
        sections.append(_render_aproxy(config))
    if config.dockerhub_mirror:
        sections.append(_render_dockerhub_mirror(config.dockerhub_mirror))
    sections.append(_render_static_host_prep())
    sections.append("# ===== end charm-injected pre-install setup =====\n")
    return "\n".join(sections)


def render_pre_job_hooks(config: RunnerConfig) -> str:
    """Render the runner ``env`` file and GitHub job-start hook.

    The hook file (``pre-job.j2`` in production) sets up the OpenTelemetry
    collector, when configured, and appends the operator's ``pre-job-script``.
    The docker mirror and OTEL endpoint are exported via the runner ``env`` file
    (``env.j2`` in production), read once per job by the runner service.

    Args:
        config: The runner options to render.

    Returns:
        A bash snippet, terminated by a newline.
    """
    otel_endpoint = ""
    if config.otel_collector_endpoint:
        # Strip CR/LF so a databag value can't inject extra env entries or extra
        # lines into the otelcol config (the databag is a trust boundary,
        # regardless of configurator validation).
        otel_endpoint = config.otel_collector_endpoint.replace("\r", "").replace("\n", "")

    hook_body = _render_pre_job_hook_body(config, otel_endpoint)

    env_entries = []
    if config.dockerhub_mirror:
        env_entries.append(f"DOCKERHUB_MIRROR={config.dockerhub_mirror}")
        env_entries.append(f"CONTAINER_REGISTRY_URL={config.dockerhub_mirror}")
    env_entries.append(f"ACTIONS_RUNNER_HOOK_JOB_STARTED={PRE_JOB_HOOK_PATH}")
    if otel_endpoint:
        env_entries.append(f"ACTION_OTEL_EXPORTER_OTLP_ENDPOINT={otel_endpoint}")

    # Pick delimiters that don't collide with the (operator-controlled) content,
    # so a pre-job-script containing the literal delimiter can't terminate the
    # heredoc early. Deterministic for a given content, keeping the rendered
    # template stable across reconciles.
    prejob_delim = _heredoc_delimiter(hook_body, "GARM_CHARM_PREJOB")
    env_delim = _heredoc_delimiter("\n".join(env_entries), "GARM_CHARM_ENV")
    return "\n".join(
        [
            "",
            "# ===== charm-injected runner job hooks =====",
            f"mkdir -p {RUNNER_HOME}",
            # Quoted delimiter: the hook file's own heredocs and $VARS must stay
            # literal here and expand only when the runner executes the hook,
            # once per job.
            f"cat > {PRE_JOB_HOOK_PATH} <<'{prejob_delim}'",
            hook_body,
            prejob_delim,
            f"chmod 0755 {PRE_JOB_HOOK_PATH}",
            f"cat >> {RUNNER_ENV_PATH} <<'{env_delim}'",
            *env_entries,
            env_delim,
            f"chown -R {RUNNER_USER}:{RUNNER_USER} {RUNNER_HOME} 2>/dev/null || true",
            "# ===== end charm-injected runner job hooks =====\n",
        ]
    )


def _render_pre_job_hook_body(config: RunnerConfig, otel_endpoint: str) -> str:
    """Render the contents of the pre-job hook file, ported from ``pre-job.j2``.

    Args:
        config: The runner options to render.
        otel_endpoint: The sanitised OTEL endpoint, or "" if unset.

    Returns:
        The full contents of the hook script (no trailing newline).
    """
    lines = ["#!/usr/bin/env bash", "set +e"]
    if otel_endpoint:
        lines.append("")
        lines.append(_OTEL_COLLECTOR_SETUP.format(endpoint=otel_endpoint))
    if config.pre_job_script:
        lines.append("")
        lines.append(_render_custom_pre_job_script(config.pre_job_script))
    return "\n".join(lines)


def _heredoc_delimiter(content: str, base: str) -> str:
    """Return a heredoc delimiter that does not appear as a line in *content*.

    Args:
        content: The heredoc body the delimiter must not collide with.
        base: The preferred delimiter; extended only if it collides.

    Returns:
        ``base``, suffixed with underscores until no line of *content* matches it.
    """
    lines = content.splitlines()
    delimiter = base
    while delimiter in lines:
        delimiter += "_"
    return delimiter


# Ported verbatim from pre-job.j2 (the `{% if otel_collector_endpoint %}` block,
# lines 136-290): sets up the OpenTelemetry collector's hostmetrics/otlp/loki
# pipelines. `$GITHUB_*`, `$RUNNER_NAME` and `$(uname -m)` are left as literal
# shell syntax — they sit inside the *inner*, unquoted `tee <<EOF` heredoc, so
# they only expand when the runner executes this hook, once per job. Only the
# exporter endpoint is substituted at render time.
_OTEL_COLLECTOR_SETUP = """\
/usr/bin/logger -s "OpenTelemetry collector is enabled."
/usr/bin/logger -s "Additional OpenTelemetery collector configuration can be added."
/usr/bin/logger -s "The exporter endpoint is at the environment variable \
ACTION_OTEL_EXPORTER_OTLP_ENDPOINT."
/usr/bin/sudo /usr/bin/mkdir -p /etc/otelcol/config.d
/usr/bin/sudo /usr/bin/touch /etc/otelcol/config.d/github.yaml
/usr/bin/sudo /usr/bin/tee /etc/otelcol/config.d/github.yaml <<EOF
receivers:
  hostmetrics:
    collection_interval: 10s
    scrapers:
      cpu:
        metrics:
          system.cpu.logical.count:
            enabled: true
          system.cpu.physical.count:
            enabled: true
      memory:
      disk:
      filesystem:
      network:
      load:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:44317
      http:
        endpoint: 0.0.0.0:44318
  loki:
    protocols:
      http:
        endpoint: 0.0.0.0:43100
    use_incoming_timestamp: true
  filelog/aproxy:
    include:
      - /var/log/syslog
    operators:
      - type: filter
        expr: 'body not matches "aproxy.aproxy"'
processors:
  attributes/self_hosted_runner_github_labels:
    actions:
      - key: service.name
        action: upsert
        value: "self-hosted-runner"
      - key: github.repository
        action: upsert
        value: "$GITHUB_REPOSITORY"
      - key: github.runner
        action: upsert
        value: "$RUNNER_NAME"
      - key: github.workflow
        action: upsert
        value: "$GITHUB_WORKFLOW"
      - key: github.job
        action: upsert
        value: "$GITHUB_JOB"
      - key: github.run.id
        action: upsert
        value: "$GITHUB_RUN_ID"
      - key: github.run.attempt
        action: upsert
        value: "$GITHUB_RUN_ATTEMPT"
      - key: host.arch
        action: upsert
        value: "$(uname -m)"
  resource/self_hosted_runner_github_labels:
    attributes:
      - key: service.name
        action: upsert
        value: "self-hosted-runner"
      - key: github.repository
        action: upsert
        value: "$GITHUB_REPOSITORY"
      - key: github.runner
        action: upsert
        value: "$RUNNER_NAME"
      - key: github.workflow
        action: upsert
        value: "$GITHUB_WORKFLOW"
      - key: github.job
        action: upsert
        value: "$GITHUB_JOB"
      - key: github.run.id
        action: upsert
        value: "$GITHUB_RUN_ID"
      - key: github.run.attempt
        action: upsert
        value: "$GITHUB_RUN_ATTEMPT"
      - key: host.arch
        action: upsert
        value: "$(uname -m)"
  resource/self_hosted_runner_github_aproxy_labels:
    attributes:
      - key: service.name
        action: upsert
        value: "aproxy"
  transform/self_hosted_runner_loki_labels:
    log_statements:
      - context: resource
        statements:
          - >
            set(resource.attributes["loki.resource.labels"],
            Concat([resource.attributes["loki.resource.labels"],
            ", service.name, github.repository, github.runner, github.workflow, github.job, \
github.run.id, github.run.attempt, host.arch"], ""))
            where resource.attributes["loki.resource.labels"] != nil
          - >
            set(resource.attributes["loki.resource.labels"],
            "service.name, github.repository, github.runner, github.workflow, github.job, \
github.run.id, github.run.attempt, host.arch")
            where resource.attributes["loki.resource.labels"] == nil
  batch:
exporters:
  otlp/self_hosted_runner:
    endpoint: {endpoint}
    tls:
      insecure: true
service:
  pipelines:
    metrics:
      receivers: [hostmetrics]
      processors: [attributes/self_hosted_runner_github_labels, batch]
      exporters: [otlp/self_hosted_runner]
    metrics/otlp:
      receivers: [otlp]
      processors: [attributes/self_hosted_runner_github_labels, batch]
      exporters: [otlp/self_hosted_runner]
    logs/otlp:
      receivers: [otlp]
      processors:
        - resource/self_hosted_runner_github_labels
        - transform/self_hosted_runner_loki_labels
        - batch
      exporters: [otlp/self_hosted_runner]
    logs/loki:
      receivers: [loki]
      processors:
        - resource/self_hosted_runner_github_labels
        - transform/self_hosted_runner_loki_labels
        - batch
      exporters: [otlp/self_hosted_runner]
    logs/aproxy:
      receivers: [filelog/aproxy]
      processors:
        - resource/self_hosted_runner_github_labels
        - resource/self_hosted_runner_github_aproxy_labels
        - transform/self_hosted_runner_loki_labels
        - batch
      exporters: [otlp/self_hosted_runner]
    traces:
      receivers: [otlp]
      processors: [resource/self_hosted_runner_github_labels, batch]
      exporters: [otlp/self_hosted_runner]
EOF

/usr/bin/sudo /usr/bin/snap enable opentelemetry-collector
/usr/bin/sudo /usr/bin/snap start opentelemetry-collector"""


def _render_custom_pre_job_script(script: str) -> str:
    """Render the custom pre-job script block, ported from ``pre-job.j2``.

    Writes the operator script to a temp file, runs it, and removes it — a
    failure is logged but never aborts the job (``pre-job.j2`` lines 300-308).

    Args:
        script: The operator-provided pre-job-script content, inserted verbatim
            (mirrors the template's ``| safe`` filter).

    Returns:
        A bash snippet.
    """
    delim = _heredoc_delimiter(script, "GARM_CHARM_CUSTOM_PREJOB")
    return "\n".join(
        [
            f"cat > /tmp/custom_pre_job_script <<'{delim}'",
            script,
            delim,
            "chmod +x /tmp/custom_pre_job_script",
            'logger -s "Running custom pre-job script"',
            '/tmp/custom_pre_job_script || logger -s "Custom pre-job script failed, '
            'continuing with the job"',
            'rm /tmp/custom_pre_job_script || logger -s "Failed to remove custom pre-job script"',
        ]
    )


def _render_aproxy(config: RunnerConfig) -> str:
    """Render aproxy install + nftables redirect rules.

    Ported from ``openstack-userdata.sh.j2`` lines 13-38: aproxy listens on
    ``:54969`` and an nftables DNAT ruleset (written to ``/etc/nftables.conf``)
    redirects egress traffic to it, both for locally-initiated connections
    (``output`` chain) and forwarded ones (``prerouting`` chain).

    Args:
        config: The runner options (uses proxy, exclude addresses, redirect ports).

    Returns:
        A bash snippet configuring aproxy as a transparent forward proxy.
    """
    # Defensively re-validate the relation-provided values before rendering them
    # into a root-executed nft ruleset: the databag is a trust boundary, so never
    # rely on the configurator's validation alone — drop anything malformed.
    ports = _valid_port_tokens(config.aproxy_redirect_ports) or ["80", "443"]
    nft_ports = ", ".join(ports)
    excludes = _valid_ipv4_tokens(config.aproxy_exclude_addresses)
    exclude_elements = ", ".join(["127.0.0.0/8", *excludes])
    dnat_rule = (
        f"ip daddr != @exclude tcp dport {{ {nft_ports} }} counter dnat to \\$default-ipv4:54969"
    )

    return "\n".join(
        [
            "# Transparently forward runner egress through the configured HTTP proxy.",
            "snap install aproxy --edge",
            f"snap set aproxy proxy={shlex.quote(config.runner_http_proxy)} listen=:54969",
            # Unquoted heredoc: `$(ip route ...)` must expand now, at boot, to
            # compute the default gateway. `\$default-ipv4` stays escaped so the
            # literal two characters `$default-ipv4` land in the file, which nft
            # itself resolves against the `define` above when it loads the file.
            "cat << EOF > /etc/nftables.conf",
            "define default-ipv4 = $(ip route get $(ip route show 0.0.0.0/0 "
            "| grep -oP 'via \\K\\S+') | grep -oP 'src \\K\\S+')",
            "table ip aproxy",
            "flush table ip aproxy",
            "table ip aproxy {",
            "      set exclude {",
            "          type ipv4_addr;",
            "          flags interval; auto-merge;",
            f"          elements = {{ {exclude_elements} }}",
            "      }",
            "      chain prerouting {",
            "              type nat hook prerouting priority dstnat; policy accept;",
            f"              {dnat_rule}",
            "      }",
            "      chain output {",
            "              type nat hook output priority -100; policy accept;",
            f"              {dnat_rule}",
            "      }",
            "}",
            "EOF",
            "systemctl enable nftables.service",
            "nft -f /etc/nftables.conf",
        ]
    )


def _render_dockerhub_mirror(mirror: str) -> str:
    """Render Docker daemon config pointing at the registry mirror.

    Ported from ``openstack-userdata.sh.j2`` lines 77-81.

    Args:
        mirror: The registry mirror URL.

    Returns:
        A bash snippet writing /etc/docker/daemon.json and restarting docker.
    """
    daemon_json = json.dumps({"registry-mirrors": [mirror]})
    return "\n".join(
        [
            "# Point Docker at the configured registry mirror.",
            "mkdir -p /etc/docker",
            "cat > /etc/docker/daemon.json <<'GARM_CHARM_DOCKER'",
            daemon_json,
            "GARM_CHARM_DOCKER",
            "systemctl daemon-reload",
            "systemctl restart docker",
        ]
    )


def _render_static_host_prep() -> str:
    """Render the always-on host-preparation steps ported from the old charm.

    Ported from ``openstack-userdata.sh.j2`` lines 74-75 (``adduser ubuntu
    lxd``/``adduser ubuntu adm``), targeting GARM's runner account instead.

    Returns:
        A bash snippet. Each command is guarded by ``|| true`` so it is a no-op
        if the runner account doesn't exist yet.
    """
    return "\n".join(
        [
            "# Static runner host preparation (ported from the github-runner charm).",
            f"adduser {RUNNER_USER} lxd || true",
            f"adduser {RUNNER_USER} adm || true",
        ]
    )


def _valid_port_tokens(spec: str) -> list[str]:
    """Return only the in-range port / N-M range tokens from a comma list.

    A token is kept only if it is ``N`` or ``N-M`` with every port in 1..65535
    and ``N <= M`` — out-of-range or inverted tokens are dropped so they can't
    break the nft ruleset.

    Args:
        spec: A comma-separated ports string (possibly empty or untrusted).

    Returns:
        The subset of well-formed, in-range tokens.
    """
    valid: list[str] = []
    for raw in spec.split(","):
        token = raw.strip()
        if not _PORT_TOKEN_RE.match(token):
            continue
        ports = [int(part) for part in token.split("-")]
        if all(1 <= port <= 65535 for port in ports) and ports == sorted(ports):
            valid.append(token)
    return valid


def _valid_ipv4_tokens(spec: str) -> list[str]:
    """Return only the valid IPv4 address/CIDR tokens from a comma list.

    Args:
        spec: A comma-separated address string (possibly empty or untrusted).

    Returns:
        The subset of tokens that parse as IPv4 networks.
    """
    valid: list[str] = []
    for token in spec.split(","):
        token = token.strip()
        try:
            network = ipaddress.ip_network(token, strict=False)
        except ValueError:
            continue
        if network.version == 4:
            valid.append(token)
    return valid
