# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Unit tests for the enable_log_forwarding action script."""

import importlib
import json
import pathlib
import sys
import tempfile
from typing import Any

ACTION_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ACTION_DIR))

module: Any = importlib.import_module("enable_log_forwarding")


def test_parse_files_into_list():
    """
    arrange: prepare comma/newline-separated file input with extra empty tokens.
    act: parse the files input into a normalized list.
    assert: parsed output keeps only non-empty, trimmed file paths.
    """
    # Arrange
    files_input = " /var/log/a.log,\n/var/log/b.log ,, /var/log/c*.log\n"

    # Act
    parsed = module.parse_files_into_list(files_input)

    # Assert
    assert parsed == ["/var/log/a.log", "/var/log/b.log", "/var/log/c*.log"]


def test_resolve_endpoint_prefers_input(monkeypatch):
    """
    arrange: set both explicit input and fallback endpoint environment variables.
    act: resolve the endpoint used by the action.
    assert: explicit input endpoint takes precedence over fallback.
    """
    # Arrange
    monkeypatch.setenv("INPUT_OTLP_ENDPOINT", "input-endpoint:4318")
    monkeypatch.setenv("ACTION_OTEL_EXPORTER_OTLP_ENDPOINT", "system-endpoint:4318")

    # Act
    resolved = module.resolve_endpoint()

    # Assert
    assert resolved == "input-endpoint:4318"


def test_resolve_endpoint_falls_back_to_action_env(monkeypatch):
    """
    arrange: set empty explicit input and a workflow-provided fallback endpoint.
    act: resolve the endpoint used by the action.
    assert: fallback workflow endpoint is returned.
    """
    # Arrange
    monkeypatch.setenv("INPUT_OTLP_ENDPOINT", "")
    monkeypatch.setenv("ACTION_OTEL_EXPORTER_OTLP_ENDPOINT", "system-endpoint:4318")

    # Act
    resolved = module.resolve_endpoint()

    # Assert
    assert resolved == "system-endpoint:4318"


def test_is_github_hosted_runner_detects_github_hosted(monkeypatch):
    """
    arrange: set RUNNER_ENVIRONMENT to github-hosted.
    act: check whether runner is github-hosted.
    assert: returns True.
    """
    # Arrange
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")

    # Act
    is_github_hosted = module.is_github_hosted_runner()

    # Assert
    assert is_github_hosted is True


def test_is_github_hosted_runner_detects_non_github_hosted(monkeypatch):
    """
    arrange: set RUNNER_ENVIRONMENT to self-hosted.
    act: check whether runner is github-hosted.
    assert: returns False.
    """
    # Arrange
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")

    # Act
    is_github_hosted = module.is_github_hosted_runner()

    # Assert
    assert is_github_hosted is False


def test_main_skips_configuration_on_github_hosted(monkeypatch):
    """
    arrange: set github-hosted environment and guard setup functions.
    act: run main.
    assert: setup functions are not called and action exits successfully.
    """
    # Arrange
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")

    def _should_not_be_called() -> str:
        raise AssertionError("read_files_input should not be called")

    monkeypatch.setattr(module, "read_files_input", _should_not_be_called)

    # Act
    module.main()


def test_build_config_adds_exporter_when_missing(monkeypatch):
    """
    arrange: define GitHub metadata env vars.
    act: build and parse collector config for selected log files.
    assert: config includes receiver paths, pipeline exporter, and exporter endpoint.
    """
    # Arrange
    monkeypatch.setenv("GITHUB_REPOSITORY", "canonical/github-runner-operators")
    monkeypatch.setenv("RUNNER_NAME", "runner-1")
    monkeypatch.setenv("GITHUB_WORKFLOW", "CI")
    monkeypatch.setenv("GITHUB_JOB", "test")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")

    # Act
    raw = module.build_config(["/var/log/syslog"], "otel:4318", module.EXPORTER_NAME)
    config = json.loads(raw)

    # Assert
    assert config["receivers"]["filelog/github_runner_optin"]["include"] == [
        "/var/log/syslog"
    ]
    assert config["service"]["pipelines"]["logs/github_runner_optin"]["exporters"] == [
        module.EXPORTER_NAME
    ]
    assert config["exporters"][module.EXPORTER_NAME]["endpoint"] == "otel:4318"


def test_build_config_skips_exporter_when_define_exporter_is_false(monkeypatch):
    """
    arrange: define GitHub metadata env vars.
    act: build config with define_exporter=False.
    assert: config has no exporters block but still references the exporter in the pipeline.
    """
    # Arrange
    monkeypatch.setenv("GITHUB_REPOSITORY", "canonical/github-runner-operators")
    monkeypatch.setenv("RUNNER_NAME", "runner-1")
    monkeypatch.setenv("GITHUB_WORKFLOW", "CI")
    monkeypatch.setenv("GITHUB_JOB", "test")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")

    # Act
    raw = module.build_config(
        ["/var/log/syslog"], "otel:4318", module.EXPORTER_NAME, define_exporter=False
    )
    config = json.loads(raw)

    # Assert
    assert "exporters" not in config
    assert config["service"]["pipelines"]["logs/github_runner_optin"]["exporters"] == [
        module.EXPORTER_NAME
    ]


def test_exporter_exists_in_config_dir_finds_exporter():
    """
    arrange: write a YAML config file containing the fixed exporter name.
    act: check whether that exporter exists in the config directory.
    assert: returns True when the exporter is present in another file.
    """
    # Arrange
    with tempfile.TemporaryDirectory() as config_dir:
        existing = pathlib.Path(config_dir) / "91-other.yaml"
        existing.write_text(
            f"exporters:\n  {module.EXPORTER_NAME}:\n    endpoint: otel:4317\n"
        )
        exclude = str(pathlib.Path(config_dir) / "91-optin.logs.yaml")

        # Act
        found = module.exporter_exists_in_config_dir(
            module.EXPORTER_NAME, config_dir, exclude
        )

    # Assert
    assert found is True


def test_exporter_exists_in_config_dir_ignores_exclude_path():
    """
    arrange: write a YAML config file with the exporter, but mark it as the excluded path.
    act: check whether the exporter exists excluding that file.
    assert: returns False since the only matching file is excluded.
    """
    # Arrange
    with tempfile.TemporaryDirectory() as config_dir:
        target = pathlib.Path(config_dir) / "90-github-runner-log-forwarding.yaml"
        target.write_text(
            f"exporters:\n  {module.EXPORTER_NAME}:\n    endpoint: otel:4317\n"
        )

        # Act
        found = module.exporter_exists_in_config_dir(
            module.EXPORTER_NAME, config_dir, str(target)
        )

    # Assert
    assert found is False


def test_exporter_exists_in_config_dir_finds_exporter_in_json():
    """
    arrange: write a JSON config file containing the fixed exporter name.
    act: check whether that exporter exists in the config directory.
    assert: returns True when the exporter is present in a JSON fragment.
    """
    # Arrange
    with tempfile.TemporaryDirectory() as config_dir:
        existing = pathlib.Path(config_dir) / "91-other.json"
        existing.write_text(
            "{\n"
            '  "exporters": {\n'
            f'    "{module.EXPORTER_NAME}": {{\n'
            '      "endpoint": "otel:4317"\n'
            "    }\n"
            "  }\n"
            "}\n"
        )
        exclude = str(pathlib.Path(config_dir) / "91-optin.logs.yaml")

        # Act
        found = module.exporter_exists_in_config_dir(
            module.EXPORTER_NAME, config_dir, exclude
        )

    # Assert
    assert found is True


def test_resolve_endpoint_exits_when_no_endpoint_set(monkeypatch):
    """
    arrange: ensure both endpoint environment variables are unset.
    act: resolve the endpoint.
    assert: exits with status code 1 when no endpoint is available.
    """
    # Arrange
    monkeypatch.delenv("INPUT_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("ACTION_OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    # Act
    try:
        module.resolve_endpoint()
    except SystemExit as error:
        exit_code = error.code
    else:
        exit_code = None

    # Assert
    assert exit_code == 1
