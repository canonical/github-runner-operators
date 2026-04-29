# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Unit tests for the enable_log_forwarding action script."""

import importlib
import json
import pathlib
import sys
import tempfile
from typing import Any

import pytest

ACTION_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ACTION_DIR))

module: Any = importlib.import_module("enable_log_forwarding")


@pytest.mark.parametrize(
    ("files_input", "expected"),
    [
        (
            " /var/log/a.log,\n/var/log/b.log ,, /var/log/c*.log\n",
            ["/var/log/a.log", "/var/log/b.log", "/var/log/c*.log"],
        ),
        (
            "\n/var/log/only.log\n",
            ["/var/log/only.log"],
        ),
    ],
)
def test_parse_files_into_list(files_input: str, expected: list[str]):
    """
    arrange: provide comma/newline-separated files input variants.
    act: parse the files input into a normalized list.
    assert: output keeps only non-empty, trimmed file paths.
    """
    # Arrange

    # Act
    parsed = module.parse_files_into_list(files_input)

    # Assert
    assert parsed == expected


@pytest.mark.parametrize(
    ("input_endpoint", "fallback_endpoint", "expected_endpoint"),
    [
        ("input-endpoint:4318", "system-endpoint:4318", "input-endpoint:4318"),
        ("", "system-endpoint:4318", "system-endpoint:4318"),
    ],
)
def test_resolve_endpoint_uses_input_then_fallback(
    monkeypatch, input_endpoint: str, fallback_endpoint: str, expected_endpoint: str
):
    """
    arrange: set explicit input and fallback endpoint environment variables.
    act: resolve the endpoint used by the action.
    assert: resolver returns explicit input first, otherwise fallback endpoint.
    """
    # Arrange
    monkeypatch.setenv("INPUT_OTLP_ENDPOINT", input_endpoint)
    monkeypatch.setenv("ACTION_OTEL_EXPORTER_OTLP_ENDPOINT", fallback_endpoint)

    # Act
    resolved = module.resolve_endpoint()

    # Assert
    assert resolved == expected_endpoint


@pytest.mark.parametrize(
    ("runner_environment", "expected"),
    [
        ("github-hosted", True),
        ("self-hosted", False),
    ],
)
def test_is_github_hosted_runner_detection(
    monkeypatch, runner_environment: str, expected: bool
):
    """
    arrange: set RUNNER_ENVIRONMENT for different runner types.
    act: check whether runner is github-hosted.
    assert: returns expected boolean per runner environment.
    """
    # Arrange
    monkeypatch.setenv("RUNNER_ENVIRONMENT", runner_environment)

    # Act
    is_github_hosted = module.is_github_hosted_runner()

    # Assert
    assert is_github_hosted is expected


@pytest.mark.parametrize("runner_environment", ["github-hosted", "GITHUB-HOSTED"])
def test_main_skips_configuration_on_github_hosted(
    monkeypatch, runner_environment: str
):
    """
    arrange: set github-hosted environment variants and guard setup functions.
    act: run main.
    assert: setup functions are not called and action exits successfully.
    """
    # Arrange
    monkeypatch.setenv("RUNNER_ENVIRONMENT", runner_environment)

    def _should_not_be_called() -> str:
        raise AssertionError("read_files_input should not be called")

    monkeypatch.setattr(module, "read_files_input", _should_not_be_called)

    # Act
    module.main()


@pytest.mark.parametrize(
    ("define_exporter", "has_exporters_block"),
    [
        (True, True),
        (False, False),
    ],
)
def test_build_config_exporter_block_is_conditionally_defined(
    monkeypatch, define_exporter: bool, has_exporters_block: bool
):
    """
    arrange: define GitHub metadata env vars.
    act: build and parse collector config for selected log files.
    assert: exporter block is included only when define_exporter is True.
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
        ["/var/log/syslog"],
        "otel:4318",
        module.EXPORTER_NAME,
        define_exporter=define_exporter,
    )
    config = json.loads(raw)

    # Assert
    assert config["receivers"]["filelog/github_runner_optin"]["include"] == [
        "/var/log/syslog"
    ]
    assert config["service"]["pipelines"]["logs/github_runner_optin"]["exporters"] == [
        module.EXPORTER_NAME
    ]
    assert ("exporters" in config) is has_exporters_block
    if has_exporters_block:
        assert config["exporters"][module.EXPORTER_NAME]["endpoint"] == "otel:4318"


@pytest.mark.parametrize(
    ("file_name", "content", "expected"),
    [
        (
            "91-other.yaml",
            f"exporters:\n  {module.EXPORTER_NAME}:\n    endpoint: otel:4317\n",
            True,
        ),
        (
            "91-other.json",
            "{\n"
            '  "exporters": {\n'
            f'    "{module.EXPORTER_NAME}": {{\n'
            '      "endpoint": "otel:4317"\n'
            "    }\n"
            "  }\n"
            "}\n",
            True,
        ),
        (
            "91-other.yaml",
            f"receivers:\n  {module.EXPORTER_NAME}:\n    endpoint: otel:4317\n",
            False,
        ),
    ],
)
def test_exporter_exists_in_config_dir_detects_supported_formats_and_sections(
    file_name: str, content: str, expected: bool
):
    """
    arrange: prepare config fragments in different formats and sections.
    act: check whether exporter exists in the config directory.
    assert: returns True only when exporter is defined under exporters in supported formats.
    """
    # Arrange
    with tempfile.TemporaryDirectory() as config_dir:
        existing = pathlib.Path(config_dir) / file_name
        existing.write_text(content)
        exclude = str(pathlib.Path(config_dir) / "91-optin.logs.yaml")

        # Act
        found = module.exporter_exists_in_config_dir(
            module.EXPORTER_NAME, config_dir, exclude
        )

    # Assert
    assert found is expected


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
