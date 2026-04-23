#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

CONFIG_DIR = "/etc/otelcol/config.d"
EXPORTER_NAME = "otlp_grpc"


def run_as_root(*args):
    if os.geteuid() == 0: # if running as root
        return subprocess.run(args, capture_output=True)
    if shutil.which("sudo"): # if sudo is available
        return subprocess.run(["sudo", *args], capture_output=True)
    print("This action requires root privileges to update collector config.", file=sys.stderr)
    sys.exit(1)


def parse_files_into_list(files_input):
    entries = []
    # Split on commas or newlines, and strip whitespace. Ignore empty entries.
    for item in re.split(r"[,\n]", files_input):
        stripped = item.strip()
        if stripped:
            entries.append(stripped)
    return entries


def resolve_endpoint():
    # If INPUT_OTLP_ENDPOINT is not set, fall back to ACTION_OTEL_EXPORTER_OTLP_ENDPOINT
    for env_var in (
        "INPUT_OTLP_ENDPOINT",
        "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val
    return ""


def check_exporter_exists():
    # Check for "  otlp_grpc:" exporter definition
    pattern = f"^  {re.escape(EXPORTER_NAME)}:[ \t]*$"
    if run_as_root("test", "-d", CONFIG_DIR).returncode != 0:
        return False
    # Search for the exporter definition in all files under CONFIG_DIR
    if run_as_root("grep", "-RqsE", pattern, CONFIG_DIR).returncode == 0:
        return True
    return False


def build_config(files, resolved_endpoint, exporter_already_exists):
    attrs = [
        ("github.repository", os.environ.get("GITHUB_REPOSITORY", "unknown")),
        ("github.runner.name", os.environ.get("RUNNER_NAME", "unknown")),
        ("github.workflow", os.environ.get("GITHUB_WORKFLOW", "unknown")),
        ("github.job.id", os.environ.get("GITHUB_JOB", "unknown")),
        ("github.run.id", os.environ.get("GITHUB_RUN_ID", "unknown")),
        ("github.run.attempt", os.environ.get("GITHUB_RUN_ATTEMPT", "unknown")),
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
        config["exporters"] = {
            EXPORTER_NAME: {"endpoint": resolved_endpoint}
        }
    return json.dumps(config, indent=2) + "\n"


def main():
    files_input = os.environ.get("INPUT_FILES", "").strip()
    if not files_input:
        print("Input 'files' cannot be empty.", file=sys.stderr)
        sys.exit(1)

    config_file_name = os.environ.get("INPUT_CONFIG_FILE_NAME", "90-github-runner-log-forwarding.yaml").strip()
    if "/" in config_file_name:
        print("Input 'config-file-name' must not include directory separators.", file=sys.stderr)
        sys.exit(1)

    config_path = os.path.join(CONFIG_DIR, config_file_name)

    if shutil.which("snap") is None:
        print("Required command is missing: snap", file=sys.stderr)
        sys.exit(1)

    if subprocess.run(["snap", "list", "opentelemetry-collector"], capture_output=True).returncode != 0:
        print("opentelemetry-collector snap is not installed on this runner.", file=sys.stderr)
        sys.exit(1)

    files = parse_files_into_list(files_input)
    if not files:
        print("Input 'files' must contain at least one path or glob.", file=sys.stderr)
        sys.exit(1)

    resolved_endpoint = resolve_endpoint()
    exporter_already_exists = check_exporter_exists()

    if not exporter_already_exists and not resolved_endpoint:
        print(
            f"Exporter '{EXPORTER_NAME}' was not found in scanned collector config directories and no OTLP endpoint was provided.",
            file=sys.stderr,
        )
        print(
            "Set input 'otlp-endpoint', or expose ACTION_OTEL_EXPORTER_OTLP_ENDPOINT to this workflow.",
            file=sys.stderr,
        )
        sys.exit(1)

    config_content = build_config(files, resolved_endpoint, exporter_already_exists)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write(config_content)
        tmp_path = tmp.name

    try:
        run_as_root("mkdir", "-p", CONFIG_DIR) # create if missing, do nothing if exists
        run_as_root("install", "-m", "0644", tmp_path, config_path) # owner read/write and group/other read permissions
    finally:
        os.unlink(tmp_path)

    print(f"Wrote log-forwarding collector config to: {config_path}")

    run_as_root("snap", "restart", "opentelemetry-collector")
    print("Restarted opentelemetry-collector to apply log-forwarding config.")


if __name__ == "__main__":
    main()
