# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the runner-install template rendering."""

import pytest

from runner_template import (
    RUNNER_ENV_PATH,
    RunnerConfig,
    build_template_data,
)

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


# A fully-populated config injects every option into the template while keeping
# the base bootstrap intact and placed after the shebang but before `set -e`.
def test_build_template_data_injects_all_options():
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
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=http://otel.example.com:4318" in result
    assert "echo hello-from-operator" in result
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=" in result
    assert RUNNER_ENV_PATH in result


# An empty config still wires the job-start hook and static host prep, but emits
# none of the optional proxy/mirror/telemetry blocks.
def test_build_template_data_empty_config_omits_optional_blocks():
    result = build_template_data(SAMPLE_BASE, RunnerConfig()).decode()

    assert "echo original-bootstrap" in result
    assert "ACTIONS_RUNNER_HOOK_JOB_STARTED=" in result
    assert "usermod -aG lxd,adm ubuntu" in result

    assert "snap install aproxy" not in result
    assert "registry-mirrors" not in result
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in result


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
            "OTEL_EXPORTER_OTLP_ENDPOINT=http://o.test:4318",
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
    result = build_template_data(SAMPLE_BASE, config).decode()
    assert present in result
    assert absent not in result


# The consumer side defensively drops malformed/IPv6 tokens (the databag is a
# trust boundary; the values are rendered into a root-executed nft ruleset).
def test_aproxy_render_drops_malformed_tokens():
    config = RunnerConfig(
        runner_http_proxy="http://p.test:3128",
        aproxy_redirect_ports="80,not-a-port,8000-9000,99 rm,99999,443-80",
        aproxy_exclude_addresses="10.0.0.0/8,evil;,2001:db8::1",
    )
    result = build_template_data(SAMPLE_BASE, config).decode()

    assert "{ 80, 8000-9000 }" in result
    assert "not-a-port" not in result
    assert "99999" not in result  # out of range
    assert "443-80" not in result  # inverted range
    assert "10.0.0.0/8" in result
    assert "evil" not in result
    assert "2001:db8::1" not in result  # IPv6 dropped: the nft table is IPv4-only


# from_databag maps each contract key into the config and ignores absent keys;
# has_config reflects whether any option is set.
def test_runner_config_from_databag_and_has_config():
    empty = RunnerConfig.from_databag({})
    assert empty == RunnerConfig()
    assert not empty.has_config()

    populated = RunnerConfig.from_databag(
        {"dockerhub_mirror": " https://m.test ", "irrelevant": "x"}
    )
    assert populated.dockerhub_mirror == "https://m.test"
    assert populated.has_config()
