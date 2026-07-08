# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the runner-install template rendering."""

import pytest

from charm_state import RunnerConfig
from runner_template import RUNNER_ENV_PATH, build_template_data

SAMPLE_BASE = b"#!/bin/bash\nset -e\necho original-bootstrap\n"


def _full_config() -> RunnerConfig:
    return RunnerConfig(
        dockerhub_mirror="https://mirror.example.com",
        runner_http_proxy="http://proxy.example.com:3128",
        aproxy_exclude_addresses="10.0.0.0/8,192.168.1.5",
        aproxy_redirect_ports="80,443,8000-9000",
        otel_collector_endpoint="http://otel.example.com:4318",
        pre_job_script="echo hello-from-operator",
    )


def test_build_template_data_injects_all_options():
    """
    arrange: A bootstrap script and a runner config with every optional field set.
    act: Build the runner template data.
    assert: The rendered template preserves the bootstrap and injects every block.
    """
    result = build_template_data(SAMPLE_BASE, _full_config()).decode()
    lines = result.splitlines()

    assert lines[0] == "#!/bin/bash"
    assert "echo original-bootstrap" in result
    # Injection sits between the shebang and the base body's `set -e`.
    assert result.index("charm-injected") < result.index("set -e")

    assert "mirror.example.com" in result
    assert "registry-mirrors" in result
    assert "proxy.example.com:3128" in result
    assert "snap install aproxy" in result
    assert "10.0.0.0/8" in result and "192.168.1.5" in result
    assert "8000-9000" in result
    assert "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel.example.com:4318" in result
    assert "echo hello-from-operator" in result
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=" in result
    assert RUNNER_ENV_PATH in result

    # aproxy: correct listen port, nftables file (not a piped `nft -f -`), and
    # both the prerouting and output DNAT chains.
    # aproxy bootstrap: proxy hostname resolved into /etc/hosts before snap
    # installs aproxy, and snapd is told to use the proxy so the snap store is
    # reachable even when there is no direct internet path.
    assert "getent hosts" in result
    assert "snap set system proxy.http" in result
    assert "snap set system proxy.https" in result

    assert "listen=:54969" in result
    assert "default-ipv4" in result
    assert "/etc/nftables.conf" in result
    assert "table ip aproxy\nflush table ip aproxy" not in result
    assert "nft delete table ip aproxy 2>/dev/null || true" in result
    assert "prerouting" in result
    assert "127.0.0.0/8" in result
    assert "counter dnat to \\$default-ipv4:54969" in result

    # docker mirror: both env vars and a full daemon-reload + restart.
    assert "DOCKERHUB_MIRROR=https://mirror.example.com" in result
    assert "CONTAINER_REGISTRY_URL=https://mirror.example.com" in result
    assert "systemctl daemon-reload" in result

    # otel collector config is written to disk and enabled.
    assert "/etc/otelcol/config.d/github.yaml" in result
    assert "snap enable opentelemetry-collector" in result

    # custom pre-job script: temp-file / run / cleanup pattern.
    assert "cat > /tmp/custom_pre_job_script <<" in result
    assert "chmod +x /tmp/custom_pre_job_script" in result
    assert "rm /tmp/custom_pre_job_script" in result


def test_build_template_data_empty_config_omits_optional_blocks():
    """
    arrange: A bootstrap script and an empty runner config.
    act: Build the runner template data.
    assert: The static setup remains and all optional blocks are omitted.
    """
    result = build_template_data(SAMPLE_BASE, RunnerConfig()).decode()

    assert "echo original-bootstrap" in result
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=" in result
    assert "adduser runner lxd || true" in result
    assert "adduser runner adm || true" in result

    assert "snap install aproxy" not in result
    assert "registry-mirrors" not in result
    assert "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT" not in result


@pytest.mark.parametrize(
    "config, present, absent",
    [
        pytest.param(
            RunnerConfig(dockerhub_mirror="https://m.test"),
            "https://m.test",
            "snap install aproxy",
            id="dockerhub-mirror-only",
        ),
        pytest.param(
            RunnerConfig(runner_http_proxy="http://p.test:8080"),
            "http://p.test:8080",
            "registry-mirrors",
            id="proxy-only",
        ),
        pytest.param(
            RunnerConfig(otel_collector_endpoint="http://o.test:4318"),
            "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT=http://o.test:4318",
            "snap install aproxy",
            id="otel-only",
        ),
        pytest.param(
            RunnerConfig(pre_job_script="run-my-thing --flag"),
            "run-my-thing --flag",
            "registry-mirrors",
            id="pre-job-script-only",
        ),
    ],
)
def test_build_template_data_per_option(config, present, absent):
    """
    arrange: A bootstrap script and a runner config with exactly one optional field set.
    act: Build the runner template data.
    assert: The selected block is present and an unrelated optional block is absent.
    """
    result = build_template_data(SAMPLE_BASE, config).decode()
    assert present in result
    assert absent not in result


def test_aproxy_render_uses_configured_ports_and_excludes():
    """
    arrange: A runner config with a proxy plus well-formed redirect ports and excludes.
    act: Build the runner template data.
    assert: The nft ruleset embeds exactly those ports and addresses.
    """
    config = RunnerConfig(
        runner_http_proxy="http://p.test:3128",
        aproxy_redirect_ports="80,8000-9000",
        aproxy_exclude_addresses="10.0.0.0/8",
    )
    result = build_template_data(SAMPLE_BASE, config).decode()

    assert "tcp dport { 80, 8000-9000 }" in result
    assert "10.0.0.0/8" in result


def test_heredoc_delimiter_avoids_collision_with_pre_job_script():
    """
    arrange: A pre-job script containing the default heredoc delimiter token.
    act: Build the runner template data.
    assert: The renderer chooses a non-colliding heredoc delimiter.
    """
    config = RunnerConfig(pre_job_script="echo hi\nGARM_CHARM_PREJOB\necho bye")
    result = build_template_data(SAMPLE_BASE, config).decode()

    assert "<<'GARM_CHARM_PREJOB_'" in result
    assert "echo bye" in result


def test_build_template_data_from_untrusted_databag_drops_malformed_values():
    """
    arrange: A raw relation databag with malformed ports/addresses and newline-bearing values.
    act: Parse it via RunnerConfig.from_databag and build the runner template data.
    assert: The malformed/injected content never reaches the rendered script.
    """
    config = RunnerConfig.from_databag(
        {
            "runner_http_proxy": "http://p.test:3128",
            "aproxy_redirect_ports": "80,not-a-port,8000-9000,99999,443-80",
            "aproxy_exclude_addresses": "10.0.0.0/8,evil;,2001:db8::1",
            "otel_collector_endpoint": "http://o.test:4318\nMALICIOUS=1",
            "dockerhub_mirror": "https://m.test\nMALICIOUS=1",
        }
    )
    result = build_template_data(SAMPLE_BASE, config).decode()

    assert "tcp dport { 80, 8000-9000 }" in result
    assert "not-a-port" not in result
    assert "99999" not in result  # out of range
    assert "443-80" not in result  # inverted range
    assert "10.0.0.0/8" in result
    assert "evil" not in result
    assert "2001:db8::1" not in result  # IPv6 dropped: the nft table is IPv4-only
    assert "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT=http://o.test:4318MALICIOUS=1" in result
    assert "DOCKERHUB_MIRROR=https://m.testMALICIOUS=1" in result
    assert "CONTAINER_REGISTRY_URL=https://m.testMALICIOUS=1" in result
    assert "\nMALICIOUS=1" not in result
