#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Configure OpenTelemetry Collector log forwarding for selected runner log files."""

import json
import logging
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Sequence

CONFIG_DIR = "/etc/otelcol/config.d"
EXPORTER_NAME = "otlp/github_runner_optin"
BATCH_PROCESSOR_NAME = "batch/github_runner_optin"
SERVICE_NAME = "self-hosted-runner"
LOKI_RESOURCE_LABELS = (
    "service.name",
    "github.repository",
    "github.runner",
    "github.workflow",
    "github.job",
    "github.run.id",
    "github.run.attempt",
)
LOKI_ATTRIBUTE_LABELS = (
    "log.file.name",
    "log.file.path",
)
SNAP_CMD = Path("/usr/bin/snap")
SUDO_CMD = Path("/usr/bin/sudo")
MKDIR_CMD = Path("/usr/bin/mkdir")
CP_CMD = Path("/usr/bin/cp")
CHMOD_CMD = Path("/usr/bin/chmod")
FILES_SPLIT_PATTERN = re.compile(r"[,\n]")  # character class: split on comma or newline
SUPPORTED_CONFIG_EXTENSIONS = {".yaml", ".yml", ".json"}
# Detects the start of a top-level YAML exporters section (e.g. "exporters:").
YAML_EXPORTERS_SECTION_PATTERN = re.compile(r"^\s*exporters\s*:\s*(?:#.*)?$")
# Detects a YAML key that matches the exporter name, optionally quoted.
YAML_EXPORTER_KEY_PATTERN_TEMPLATE = r"^\s*['\"]?{exporter_name}['\"]?\s*:\s*(?:#.*)?$"
# Detects a JSON exporters object containing the exporter key.
JSON_EXPORTER_KEY_PATTERN_TEMPLATE = (
    r'"exporters"\s*:\s*\{{[\s\S]*?"{exporter_name}"\s*:'
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def run_as_root(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run a command directly as root or through sudo when available."""
    if os.geteuid() == 0:  # if running as root
        return subprocess.run(args, capture_output=True, check=False)  # nosec B603
    if SUDO_CMD.is_file():  # if sudo is available
        return subprocess.run(
            [str(SUDO_CMD), *args], capture_output=True, check=False
        )  # nosec B603
    logger.error("This action requires root privileges to update collector config.")
    sys.exit(1)


def parse_files_into_list(files_input: str) -> list[str]:
    """Parse comma/newline-separated file patterns into a normalized non-empty list."""
    entries = []
    for item in FILES_SPLIT_PATTERN.split(files_input):
        stripped = item.strip()
        if stripped:
            entries.append(stripped)

    if not entries:
        logger.error("Input 'files' must contain at least one path or glob.")
        sys.exit(1)

    return entries


def resolve_endpoint() -> str:
    """Resolve OTLP endpoint from explicit input,
    falling back to ACTION_OTEL_EXPORTER_OTLP_ENDPOINT."""
    for env_var in (
        "INPUT_OTLP_ENDPOINT",
        "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        val = os.getenv(env_var, "").strip()
        if val:
            return val

    logger.error(
        "No OTLP endpoint was provided. Set input 'otlp-endpoint', or expose "
        "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT to this workflow.",
    )
    sys.exit(1)


def is_github_hosted_runner() -> bool:
    """Return whether this action is running on a GitHub-hosted runner."""
    return os.getenv("RUNNER_ENVIRONMENT", "").strip().lower() == "github-hosted"


def _contains_exporter_in_yaml(content: str, exporter_name: str) -> bool:
    """Return whether YAML content defines exporter_name under exporters: section."""
    in_exporters = False
    exporters_indent = -1
    exporter_key_pattern = re.compile(
        YAML_EXPORTER_KEY_PATTERN_TEMPLATE.format(
            exporter_name=re.escape(exporter_name)
        )
    )

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if in_exporters:
            if indent <= exporters_indent and not stripped.startswith("-"):
                in_exporters = False
            elif exporter_key_pattern.match(line):
                return True

        if YAML_EXPORTERS_SECTION_PATTERN.match(line):
            in_exporters = True
            exporters_indent = indent

    return False


def _contains_exporter_in_json(content: str, exporter_name: str) -> bool:
    """Return whether JSON content defines exporter_name inside exporters object."""
    json_pattern = re.compile(
        JSON_EXPORTER_KEY_PATTERN_TEMPLATE.format(
            exporter_name=re.escape(exporter_name)
        ),
    )
    return bool(json_pattern.search(content))


def _read_text_file(path: Path) -> str | None:
    """Read file content safely, returning None on read errors."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _is_supported_config_file(path: Path) -> bool:
    """Return whether path is a supported config file extension."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_CONFIG_EXTENSIONS


def exporter_exists_in_config_dir(
    exporter_name: str, config_dir: str, exclude_path: str
) -> bool:
    """Check if an exporter with the given name is already defined in another config fragment."""
    config_dir_path = Path(config_dir)
    exclude = Path(exclude_path).resolve()
    if not config_dir_path.is_dir():
        return False

    for config_file in config_dir_path.iterdir():
        if not _is_supported_config_file(config_file):
            continue
        if config_file.resolve() == exclude:
            continue

        content = _read_text_file(config_file)
        if content is None:
            continue

        if config_file.suffix.lower() in {
            ".yaml",
            ".yml",
        } and _contains_exporter_in_yaml(content, exporter_name):
            return True
        if config_file.suffix.lower() == ".json" and _contains_exporter_in_json(
            content, exporter_name
        ):
            return True

    return False


def build_resource_attributes() -> list[dict[str, str]]:
    """Build static GitHub resource attributes attached to forwarded logs."""
    attrs = [
        ("service.name", SERVICE_NAME),
        ("github.repository", os.getenv("GITHUB_REPOSITORY", "unknown")),
        ("github.runner", os.getenv("RUNNER_NAME", "unknown")),
        ("github.workflow", os.getenv("GITHUB_WORKFLOW", "unknown")),
        ("github.job", os.getenv("GITHUB_JOB", "unknown")),
        ("github.run.id", os.getenv("GITHUB_RUN_ID", "unknown")),
        ("github.run.attempt", os.getenv("GITHUB_RUN_ATTEMPT", "unknown")),
        ("loki.resource.labels", ", ".join(LOKI_RESOURCE_LABELS)),
    ]
    return [{"key": key, "value": value, "action": "upsert"} for key, value in attrs]


def build_log_attribute_actions() -> list[dict[str, str]]:
    """Build log-attribute actions for Loki label promotion hints."""
    return [
        {
            "key": "loki.attribute.labels",
            "value": ", ".join(LOKI_ATTRIBUTE_LABELS),
            "action": "upsert",
        }
    ]


def build_config(
    files: Sequence[str],
    resolved_endpoint: str,
    exporter_name: str,
    define_exporter: bool = True,
) -> str:
    """Build a collector pipeline config fragment for opt-in log forwarding."""
    config: dict = {
        "receivers": {
            "filelog/github_runner_optin": {
                "include": list(files),
                "start_at": "end",
                "include_file_name": True,
                "include_file_path": True,
            }
        },
        "processors": {
            "resource/github_runner_optin": {
                "attributes": build_resource_attributes(),
            },
            "attributes/github_runner_optin": {
                "actions": build_log_attribute_actions(),
            },
            BATCH_PROCESSOR_NAME: {},
        },
        "service": {
            "pipelines": {
                "logs/github_runner_optin": {
                    "receivers": ["filelog/github_runner_optin"],
                    "processors": [
                        "resource/github_runner_optin",
                        "attributes/github_runner_optin",
                        BATCH_PROCESSOR_NAME,
                    ],
                    "exporters": [exporter_name],
                }
            }
        },
    }
    if define_exporter:
        config["exporters"] = {
            exporter_name: {
                "endpoint": resolved_endpoint,
                "tls": {"insecure": True},
            }
        }

    return json.dumps(config, indent=2)


def read_files_input() -> str:
    """Read and validate the required files input."""
    files_input = os.getenv("INPUT_FILES", "").strip()
    if not files_input:
        logger.error("Input 'files' cannot be empty.")
        sys.exit(1)
    return files_input


def read_config_file_name() -> str:
    """Read and validate the destination config file name."""
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

    return config_file_name


def ensure_collector_is_available() -> None:
    """Ensure the opentelemetry-collector snap is available on the runner."""
    if not SNAP_CMD.is_file():
        logger.error("Required command is missing: snap")
        sys.exit(1)

    snap_list_result = subprocess.run(  # nosec B603
        [str(SNAP_CMD), "list", "opentelemetry-collector"],
        capture_output=True,
        check=False,
    )
    if snap_list_result.returncode == 0:
        return

    logger.info("opentelemetry-collector is not installed; attempting installation.")
    install_result = run_as_root(str(SNAP_CMD), "install", "opentelemetry-collector")
    if install_result.returncode != 0:
        stderr = install_result.stderr.decode(errors="replace").strip()
        logger.error(
            "Failed to install opentelemetry-collector snap: %s",
            stderr or "unknown error",
        )
        sys.exit(1)
    logger.info("Installed opentelemetry-collector snap.")


def write_collector_config(config_content: str, config_path: str) -> None:
    """Write generated config to /etc/otelcol/config.d via root privileges."""
    config_path_obj = Path(config_path)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(config_content)
        tmp_path = Path(tmp.name)

    try:
        if os.geteuid() == 0:
            config_path_obj.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tmp_path, config_path_obj)
            config_path_obj.chmod(0o644)
        else:
            mkdir_result = run_as_root(str(MKDIR_CMD), "-p", CONFIG_DIR)
            if mkdir_result.returncode != 0:
                stderr = mkdir_result.stderr.decode(errors="replace").strip()
                logger.error(
                    "Failed to create collector config directory '%s': %s",
                    CONFIG_DIR,
                    stderr or "unknown error",
                )
                sys.exit(1)

            copy_result = run_as_root(str(CP_CMD), str(tmp_path), str(config_path_obj))
            if copy_result.returncode != 0:
                stderr = copy_result.stderr.decode(errors="replace").strip()
                logger.error(
                    "Failed to copy collector config to '%s': %s",
                    config_path,
                    stderr or "unknown error",
                )
                sys.exit(1)

            chmod_result = run_as_root(str(CHMOD_CMD), "0644", str(config_path_obj))
            if chmod_result.returncode != 0:
                stderr = chmod_result.stderr.decode(errors="replace").strip()
                logger.error(
                    "Failed to set collector config permissions on '%s': %s",
                    config_path,
                    stderr or "unknown error",
                )
                sys.exit(1)
    finally:
        tmp_path.unlink(missing_ok=True)

    logger.info("Wrote log-forwarding collector config to: %s", config_path)


def log_generated_config(config_content: str) -> None:
    """Emit generated config content in grouped GitHub Actions logs."""
    print("::group::Generated collector config")
    print(config_content)
    print("::endgroup::")


def restart_collector() -> None:
    """Restart collector service so new config is loaded."""
    if not SNAP_CMD.is_file():
        logger.error("Required command is missing: snap")
        sys.exit(1)

    restart_result = run_as_root(str(SNAP_CMD), "restart", "opentelemetry-collector")
    if restart_result.returncode != 0:
        stderr = restart_result.stderr.decode(errors="replace").strip()
        logger.error(
            "Failed to restart opentelemetry-collector: %s",
            stderr or "unknown error",
        )
        sys.exit(1)
    logger.info("Restarted opentelemetry-collector to apply log-forwarding config.")


def main():
    """Validate inputs, write collector config, and restart the collector service."""
    if is_github_hosted_runner():
        logger.info("GitHub-hosted runner detected; skipping collector configuration.")
        return

    files_input = read_files_input()
    config_file_name = read_config_file_name()
    config_path = str(Path(CONFIG_DIR) / config_file_name)
    ensure_collector_is_available()

    files = parse_files_into_list(files_input)

    resolved_endpoint = resolve_endpoint()
    define_exporter = not exporter_exists_in_config_dir(
        EXPORTER_NAME, CONFIG_DIR, config_path
    )

    config_content = build_config(
        files, resolved_endpoint, EXPORTER_NAME, define_exporter
    )
    log_generated_config(config_content)
    write_collector_config(config_content, config_path)
    restart_collector()


if __name__ == "__main__":
    main()
