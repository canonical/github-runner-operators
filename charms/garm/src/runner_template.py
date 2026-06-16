#!/usr/bin/env python3
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

    The hook always carries a hardcoded proxy-IP-resolution step (pins the proxy
    address for the job's lifetime) and appends the operator's ``pre-job-script``.
    The OTEL endpoint, when set, is exported via the runner ``env`` file.

    Args:
        config: The runner options to render.

    Returns:
        A bash snippet, terminated by a newline.
    """
    hook_body = _PROXY_RESOLVE_SNIPPET
    if config.pre_job_script:
        hook_body += "\n\n# --- operator-provided pre-job-script ---\n" + config.pre_job_script

    env_entries = [f"ACTIONS_RUNNER_HOOK_JOB_STARTED={PRE_JOB_HOOK_PATH}"]
    if config.otel_collector_endpoint:
        env_entries.append(f"OTEL_EXPORTER_OTLP_ENDPOINT={config.otel_collector_endpoint}")

    return "\n".join(
        [
            "",
            "# ===== charm-injected runner job hooks =====",
            f"mkdir -p {RUNNER_HOME}",
            f"cat > {PRE_JOB_HOOK_PATH} <<'GARM_CHARM_PREJOB'",
            hook_body,
            "GARM_CHARM_PREJOB",
            f"chmod 0755 {PRE_JOB_HOOK_PATH}",
            f"cat >> {RUNNER_ENV_PATH} <<'GARM_CHARM_ENV'",
            *env_entries,
            "GARM_CHARM_ENV",
            f"chown -R {RUNNER_USER}:{RUNNER_USER} {RUNNER_HOME} 2>/dev/null || true",
            "# ===== end charm-injected runner job hooks =====\n",
        ]
    )


# The production github-runner charm pins the proxy IP once per job so it cannot
# drift mid-run. The exact resolution logic is environment-specific; this is a
# faithful-but-minimal port.
# TODO(ISD-278): port the exact proxy-resolution script from
# canonical/github-runner-operator once the production source is available.
_PROXY_RESOLVE_SNIPPET = """\
#!/bin/bash
# Pin the proxy address for the duration of this job.
set -uo pipefail
if [ -n "${HTTP_PROXY:-}" ]; then
    proxy_host=$(echo "${HTTP_PROXY}" | sed -E 's#^https?://##; s#[:/].*$##')
    proxy_ip=$(getent hosts "${proxy_host}" | awk '{print $1; exit}' || true)
    if [ -n "${proxy_ip}" ]; then
        echo "${proxy_ip} ${proxy_host}" | sudo tee -a /etc/hosts >/dev/null
    fi
fi"""


def _render_aproxy(config: RunnerConfig) -> str:
    """Render aproxy install + nftables redirect rules.

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
    exclude_guard = ""
    excludes = _valid_ipv4_tokens(config.aproxy_exclude_addresses)
    if excludes:
        exclude_guard = f"ip daddr != {{ {', '.join(excludes)} }} "

    # TODO(ISD-278): confirm the exact aproxy listen port / nft ruleset against
    # the production github-runner charm cloud-init.
    return "\n".join(
        [
            "# Transparently forward runner egress through the configured HTTP proxy.",
            "snap install aproxy --edge >/dev/null 2>&1 || true",
            f"snap set aproxy proxy={shlex.quote(config.runner_http_proxy)} listen=:8443 || true",
            "nft -f - <<'GARM_CHARM_NFT' || true",
            "table ip aproxy {",
            "  chain output {",
            "    type nat hook output priority -100; policy accept;",
            f"    {exclude_guard}tcp dport {{ {nft_ports} }} counter redirect to :8443",
            "  }",
            "}",
            "GARM_CHARM_NFT",
        ]
    )


def _render_dockerhub_mirror(mirror: str) -> str:
    """Render Docker daemon config pointing at the registry mirror.

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
            "systemctl restart docker >/dev/null 2>&1 || true",
        ]
    )


def _render_static_host_prep() -> str:
    """Render the always-on host-preparation steps ported from the old charm.

    Returns:
        A bash snippet. Group membership is applied here; the remaining
        production steps are stubbed pending a faithful port.
    """
    # TODO(ISD-278): port the remaining production cloud-init steps from
    # canonical/github-runner-operator: apt mirror sync self-test, tmate proxy
    # setup, and the post-job metrics collector. Also confirm the target account
    # for these group memberships: ISD278 specifies "ubuntu", but GARM runs the
    # runner as RUNNER_USER ("runner") — reconcile against the old charm's
    # cloud-init. The command is guarded by "|| true", so it is a no-op if the
    # user is absent.
    return "\n".join(
        [
            "# Static runner host preparation (ported from the github-runner charm).",
            "usermod -aG lxd,adm ubuntu >/dev/null 2>&1 || true",
        ]
    )


def _valid_port_tokens(spec: str) -> list[str]:
    """Return only the well-formed port / N-M range tokens from a comma list.

    Args:
        spec: A comma-separated ports string (possibly empty or untrusted).

    Returns:
        The subset of tokens matching ``N`` or ``N-M`` (digits only).
    """
    return [token.strip() for token in spec.split(",") if _PORT_TOKEN_RE.match(token.strip())]


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
