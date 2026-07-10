# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the runner-install template rendering."""

import shlex

import pytest

from charm_state import RunnerConfig
from runner_template import RUNNER_ENV_PATH, build_template_data, render_aproxy_pre_install_script

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
    assert "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel.example.com:4318" in result
    assert "echo hello-from-operator" in result
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=" in result
    assert RUNNER_ENV_PATH in result

    # aproxy is delivered as a pre-install script (scaleset extra_specs), not
    # injected into the runner template — see render_aproxy_pre_install_script.
    assert "snap install aproxy" not in result

    # docker mirror: both env vars and a full daemon-reload + restart.
    assert "DOCKERHUB_MIRROR=https://mirror.example.com" in result
    assert "CONTAINER_REGISTRY_URL=https://mirror.example.com" in result
    assert "sudo systemctl daemon-reload" in result
    assert "sudo tee /etc/docker/daemon.json" in result
    assert "sudo systemctl restart docker" in result

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
    assert "sudo adduser runner lxd || true" in result
    assert "sudo adduser runner adm || true" in result

    assert "snap install aproxy" not in result
    assert "registry-mirrors" not in result
    assert "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT" not in result


@pytest.mark.parametrize(
    "config, present, absent",
    [
        pytest.param(
            RunnerConfig(dockerhub_mirror="https://m.test"),
            "https://m.test",
            "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT",
            id="dockerhub-mirror-only",
        ),
        pytest.param(
            RunnerConfig(otel_collector_endpoint="http://o.test:4318"),
            "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT=http://o.test:4318",
            "registry-mirrors",
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
    act: Render the standalone aproxy pre-install script.
    assert: The nft ruleset embeds exactly those ports and addresses.
    """
    config = RunnerConfig(
        runner_http_proxy="http://p.test:3128",
        aproxy_redirect_ports="80,8000-9000",
        aproxy_exclude_addresses="10.0.0.0/8",
    )
    result = render_aproxy_pre_install_script(config)

    assert "tcp dport { 80, 8000-9000 }" in result
    assert "10.0.0.0/8" in result


def test_render_aproxy_pre_install_script_happy_path():
    """
    arrange: A runner config with every aproxy-related field set to a realistic value.
    act: Render the standalone aproxy pre-install script.
    assert: The script is a standalone bash script that points the snap store and
        aproxy at the proxy, and installs the nftables redirect.
    """
    config = RunnerConfig(
        runner_http_proxy="http://proxy.example.com:3128",
        aproxy_exclude_addresses="10.0.0.0/8",
        aproxy_redirect_ports="80,443",
    )
    result = render_aproxy_pre_install_script(config)
    lines = result.splitlines()

    assert lines[0] == "#!/bin/bash"
    assert "set -e" not in result

    assert "snap set system proxy.http=http://proxy.example.com:3128" in result
    assert "snap set system proxy.https=http://proxy.example.com:3128" in result

    assert "snap install aproxy" in result
    assert "snap set aproxy proxy=proxy.example.com:3128 listen=:54969" in result

    assert "tcp dport { 80, 443 }" in result
    assert "10.0.0.0/8" in result
    assert "127.0.0.0/8" in result
    assert "counter dnat to \\$default-ipv4:54969" in result

    # The ruleset is piped straight into the kernel (single-use VM, no reboot),
    # not persisted to a file or nftables.service.
    assert "nft -f -" in result
    assert "/etc/nftables.conf" not in result
    assert "systemctl enable nftables" not in result

    # The nftables redirect must be gated on aproxy actually listening — a DNAT
    # to a dead :54969 would black-hole all egress rather than fall back.
    assert "snap services aproxy" in result
    assert result.index("snap services aproxy") < result.index("nft -f -")

    # Failures are logged so a broken bootstrap is visible in the console logs.
    assert "[aproxy-bootstrap]" in result
    assert "ERROR" in result


@pytest.mark.parametrize(
    "proxy, expected",
    [
        ("http://h:3128", "h:3128"),
        ("https://h:3128", "h:3128"),
        ("h:3128", "h:3128"),
        # netloc, not hostname:port — userinfo and IPv6 brackets must survive so
        # aproxy receives a usable authority for authenticated / IPv6 proxies.
        ("http://user:pass@h:3128", "user:pass@h:3128"),
        ("http://[2001:db8::1]:3128", "[2001:db8::1]:3128"),
    ],
    ids=["http-scheme", "https-scheme", "no-scheme", "userinfo", "ipv6"],
)
def test_render_aproxy_pre_install_script_strips_scheme_for_aproxy(proxy, expected):
    """
    arrange: A proxy value with a scheme, no scheme, embedded credentials, or an IPv6 host.
    act: Render the standalone aproxy pre-install script.
    assert: aproxy is configured with the bare authority (it rejects URLs) with userinfo
        and IPv6 brackets preserved.
    """
    config = RunnerConfig(runner_http_proxy=proxy)
    result = render_aproxy_pre_install_script(config)

    # The value is shlex-quoted in the script; an IPv6 authority thus renders
    # bracket-quoted, which is exactly why the assertion quotes the expectation.
    assert f"snap set aproxy proxy={shlex.quote(expected)}" in result


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
    arrange: A raw relation databag with newline-bearing otel/dockerhub values.
    act: Parse it via RunnerConfig.from_databag and build the runner template data.
    assert: Newlines are stripped so each value stays on a single line (the injected
        suffix is retained, but flattened onto the same env-file line, not a new one).
    """
    config = RunnerConfig.from_databag(
        {
            "otel_collector_endpoint": "http://o.test:4318\nMALICIOUS=1",
            "dockerhub_mirror": "https://m.test\nMALICIOUS=1",
        }
    )
    result = build_template_data(SAMPLE_BASE, config).decode()

    assert "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT=http://o.test:4318MALICIOUS=1" in result
    assert "DOCKERHUB_MIRROR=https://m.testMALICIOUS=1" in result
    assert "CONTAINER_REGISTRY_URL=https://m.testMALICIOUS=1" in result
    assert "\nMALICIOUS=1" not in result


def test_render_aproxy_pre_install_script_from_untrusted_databag_drops_malformed_values():
    """
    arrange: A raw relation databag with malformed/out-of-range ports and addresses.
    act: Parse it via RunnerConfig.from_databag and render the aproxy pre-install script.
    assert: The malformed values are dropped; well-formed ones still render.
    """
    config = RunnerConfig.from_databag(
        {
            "runner_http_proxy": "http://p.test:3128\nMALICIOUS=1",
            "aproxy_redirect_ports": "80,not-a-port,8000-9000,99999,443-80",
            "aproxy_exclude_addresses": "10.0.0.0/8,evil;,2001:db8::1",
        }
    )
    result = render_aproxy_pre_install_script(config)

    assert "tcp dport { 80, 8000-9000 }" in result
    assert "not-a-port" not in result
    assert "99999" not in result  # out of range
    assert "443-80" not in result  # inverted range
    assert "10.0.0.0/8" in result
    # A newline injected into the proxy value must not survive into the script.
    assert "\nMALICIOUS=1" not in result
    assert "evil" not in result
    assert "2001:db8::1" not in result  # IPv6 dropped: the nft table is IPv4-only
