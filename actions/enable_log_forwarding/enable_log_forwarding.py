#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Configure OpenTelemetry Collector log forwarding for selected runner log files."""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

CONFIG_DIR = "/etc/otelcol/config.d"
EXPORTER_NAME = "otlp_grpc"
SNAP_CMD = shutil.which("snap")
SUDO_CMD = shutil.which("sudo")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_as_root(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run a command directly as root or through sudo when available."""
    if os.geteuid() == 0:  # if running as root
        return subprocess.run(args, capture_output=True, check=False)
    if SUDO_CMD:  # if sudo is available
        return subprocess.run([SUDO_CMD, *args], capture_output=True, check=False)
    logger.error("This action requires root privileges to update collector config.")
    sys.exit(1)


def parse_files_into_list(files_input: str) -> list[str]:
    """Parse comma/newline-separated file patterns into a normalized list."""
    entries = []
    # Split on commas or newlines, and strip whitespace. Ignore empty entries.
    for item in re.split(r"[,\n]", files_input):
        stripped = item.strip()
        if stripped:
            entries.append(stripped)
    return entries


def resolve_endpoint() -> str:
    """Resolve OTLP endpoint from explicit input, then workflow fallback variable."""
    # If INPUT_OTLP_ENDPOINT is not set, fall back to ACTION_OTEL_EXPORTER_OTLP_ENDPOINT
    for env_var in (
        "INPUT_OTLP_ENDPOINT",
        "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        val = os.getenv(env_var, "").strip()
        if val:
            return val
    return ""


def check_exporter_exists() -> bool:
    """Return whether the configured exporter is already defined in collector config files."""
    # Check for "  otlp_grpc:" exporter definition
    pattern = f"^  {re.escape(EXPORTER_NAME)}:[ \t]*$"
    config_dir = Path(CONFIG_DIR)
    if not config_dir.is_dir():
        return False

    matcher = re.compile(pattern)
    for path in config_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if matcher.match(line):
                    return True
        except OSError:
            continue
    return False


def build_config(
    files: Sequence[str], resolved_endpoint: str, exporter_already_exists: bool
) -> str:
    """Build a collector pipeline config fragment for opt-in log forwarding."""
    attrs = [
        ("github.repository", os.getenv("GITHUB_REPOSITORY", "unknown")),
        ("github.runner.name", os.getenv("RUNNER_NAME", "unknown")),
        ("github.workflow", os.getenv("GITHUB_WORKFLOW", "unknown")),
        ("github.job.id", os.getenv("GITHUB_JOB", "unknown")),
        ("github.run.id", os.getenv("GITHUB_RUN_ID", "unknown")),
        ("github.run.attempt", os.getenv("GITHUB_RUN_ATTEMPT", "unknown")),
    ]
    config = {
        "receivers": {
            "filelog/github_runner_optin": {
                "include": files,
                "start_at": "end",
            }
        },
        "processors": {
            "resource/github_runner_optin": {
                "attributes": [
                    {"key": key, "value": value, "action": "upsert"}
                    for key, value in attrs
                ]
            }
        },
        "service": {
            "pipelines": {
                "logs/github_runner_optin": {
                    "receivers": ["filelog/github_runner_optin"],
                    "processors": ["resource/github_runner_optin", "batch"],
                    "exporters": [EXPORTER_NAME],
                }
            }
        },
    }
    if not exporter_already_exists and resolved_endpoint:
        config["exporters"] = {EXPORTER_NAME: {"endpoint": resolved_endpoint}}
    return json.dumps(config, indent=2) + "\n"


def main():
    """Validate inputs, write collector config, and restart the collector service."""
    files_input = os.getenv("INPUT_FILES", "").strip()
    if not files_input:
        logger.error("Input 'files' cannot be empty.")
        sys.exit(1)

    config_file_name = os.getenv(
        "INPUT_CONFIG_FILE_NAME", "90-github-runner-log-forwarding.yaml"
    ).strip()
    if (
        not config_file_name
        or config_file_name in {".", ".."}
        or Path(config_file_name).name != config_file_name
    ):
        logger.error(
            "Input 'config-file-name' must be a non-empty file name without directory components.",
        )
        sys.exit(1)

    config_path = str(Path(CONFIG_DIR) / config_file_name)

    if SNAP_CMD is None:
        logger.error("Required command is missing: snap")
        sys.exit(1)

    if (
        subprocess.run(
            [SNAP_CMD, "list", "opentelemetry-collector"],
            capture_output=True,
            check=False,
        ).returncode
        != 0
    ):
        logger.error("opentelemetry-collector snap is not installed on this runner.")
        sys.exit(1)

    files = parse_files_into_list(files_input)
    if not files:
        logger.error("Input 'files' must contain at least one path or glob.")
        sys.exit(1)

    resolved_endpoint = resolve_endpoint()
    exporter_already_exists = check_exporter_exists()

    if not exporter_already_exists and not resolved_endpoint:
        logger.error(
            "Exporter '%s' was not found in scanned collector config directories "
            "and no OTLP endpoint was provided.",
            EXPORTER_NAME,
        )
        logger.error(
            "Set input 'otlp-endpoint', or expose "
            "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT to this workflow.",
        )
        sys.exit(1)

    config_content = build_config(files, resolved_endpoint, exporter_already_exists)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(config_content)
        tmp_path = tmp.name

    try:
        mkdir_result = run_as_root(
            "mkdir", "-p", CONFIG_DIR  # create directory if it doesn't exist
        )
        if mkdir_result.returncode != 0:
            stderr = mkdir_result.stderr.decode(errors="replace").strip()
            logger.error(
                "Failed to create collector config directory '%s': %s",
                CONFIG_DIR,
                stderr or "unknown error",
            )
            sys.exit(1)

        install_result = run_as_root(
            "install", "-m", "0644", tmp_path, config_path  # rw-r--r-- permissions
        )
        if install_result.returncode != 0:
            stderr = install_result.stderr.decode(errors="replace").strip()
            logger.error(
                "Failed to install collector config to '%s': %s",
                config_path,
                stderr or "unknown error",
            )
            sys.exit(1)
    finally:
        os.unlink(tmp_path)

    logger.info("Wrote log-forwarding collector config to: %s", config_path)

    restart_result = run_as_root(SNAP_CMD, "restart", "opentelemetry-collector")
    if restart_result.returncode != 0:
        stderr = restart_result.stderr.decode(errors="replace").strip()
        logger.error(
            "Failed to restart opentelemetry-collector: %s",
            stderr or "unknown error",
        )
        sys.exit(1)
    logger.info("Restarted opentelemetry-collector to apply log-forwarding config.")


if __name__ == "__main__":
    main()
