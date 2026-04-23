"""Unit tests for the enable_log_forwarding action script."""

import importlib.util
import json
import pathlib
import unittest
from unittest import mock

MODULE_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "enable_log_forwarding.py"
)


def load_module(path: pathlib.Path):
    """Load the action module from file for direct function-level unit testing."""
    spec = importlib.util.spec_from_file_location("enable_log_forwarding", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module(MODULE_PATH)


class TestEnableLogForwarding(unittest.TestCase):
    """Test suite for parsing, endpoint resolution, exporter detection, and config generation."""

    def test_parse_files_into_list(self):
        """It parses comma/newline-separated inputs and drops empty entries."""
        files_input = " /var/log/a.log,\n/var/log/b.log ,, /var/log/c*.log\n"
        parsed = MODULE.parse_files_into_list(files_input)
        self.assertEqual(
            parsed, ["/var/log/a.log", "/var/log/b.log", "/var/log/c*.log"]
        )

    def test_resolve_endpoint_prefers_input(self):
        """It prefers the explicit action input endpoint over fallback env values."""
        with mock.patch.dict(
            MODULE.os.environ,
            {
                "INPUT_OTLP_ENDPOINT": "input-endpoint:4318",
                "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT": "system-endpoint:4318",
            },
            clear=False,
        ):
            resolved = MODULE.resolve_endpoint()

        self.assertEqual(resolved, "input-endpoint:4318")

    def test_resolve_endpoint_falls_back_to_action_env(self):
        """It falls back to the workflow-provided endpoint when input is empty."""
        with mock.patch.dict(
            MODULE.os.environ,
            {
                "INPUT_OTLP_ENDPOINT": "",
                "ACTION_OTEL_EXPORTER_OTLP_ENDPOINT": "system-endpoint:4318",
            },
            clear=False,
        ):
            resolved = MODULE.resolve_endpoint()

        self.assertEqual(resolved, "system-endpoint:4318")

    def test_check_exporter_exists_true(self):
        """It returns true when a collector config file defines the exporter name."""
        mock_file = mock.Mock(spec=pathlib.Path)
        mock_file.is_file.return_value = True
        mock_file.read_text.return_value = "exporters:\n  otlp_grpc:\n"

        with mock.patch.object(
            pathlib.Path, "is_dir", return_value=True
        ), mock.patch.object(pathlib.Path, "rglob", return_value=[mock_file]):
            self.assertTrue(MODULE.check_exporter_exists())

    def test_build_config_adds_exporter_when_missing(self):
        """It adds an exporter block when no pre-existing exporter is detected."""
        env = {
            "GITHUB_REPOSITORY": "canonical/github-runner-operators",
            "RUNNER_NAME": "runner-1",
            "GITHUB_WORKFLOW": "CI",
            "GITHUB_JOB": "test",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
        }
        with mock.patch.dict(MODULE.os.environ, env, clear=False):
            raw = MODULE.build_config(["/var/log/syslog"], "otel:4318", False)

        config = json.loads(raw)
        self.assertEqual(
            config["receivers"]["filelog/github_runner_optin"]["include"],
            ["/var/log/syslog"],
        )
        self.assertEqual(
            config["service"]["pipelines"]["logs/github_runner_optin"]["exporters"],
            [MODULE.EXPORTER_NAME],
        )
        self.assertEqual(
            config["exporters"][MODULE.EXPORTER_NAME]["endpoint"], "otel:4318"
        )

    def test_build_config_reuses_existing_exporter(self):
        """It omits exporter creation when an exporter already exists elsewhere."""
        with mock.patch.dict(MODULE.os.environ, {}, clear=False):
            raw = MODULE.build_config(["/var/log/syslog"], "otel:4318", True)

        config = json.loads(raw)
        self.assertNotIn("exporters", config)


if __name__ == "__main__":
    unittest.main()
