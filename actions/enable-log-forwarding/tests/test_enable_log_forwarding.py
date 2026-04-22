import importlib.util
import json
import pathlib
import types
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent / "enable-log-forwarding.py"


def load_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("enable_log_forwarding", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module(MODULE_PATH)


class TestEnableLogForwarding(unittest.TestCase):
    def test_parse_files_into_list(self):
        files_input = " /var/log/a.log,\n/var/log/b.log ,, /var/log/c*.log\n"
        parsed = MODULE.parse_files_into_list(files_input)
        self.assertEqual(parsed, ["/var/log/a.log", "/var/log/b.log", "/var/log/c*.log"])

    def test_resolve_endpoint_prefers_input(self):
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
        # First call checks directory exists, second call checks grep match.
        calls = [types.SimpleNamespace(returncode=0), types.SimpleNamespace(returncode=0)]
        with mock.patch.object(MODULE, "run_as_root", side_effect=calls):
            self.assertTrue(MODULE.check_exporter_exists())

    def test_build_config_adds_exporter_when_missing(self):
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
        self.assertEqual(config["receivers"]["filelog/github_runner_optin"]["include"], ["/var/log/syslog"])
        self.assertEqual(config["service"]["pipelines"]["logs/github_runner_optin"]["exporters"], [MODULE.EXPORTER_NAME])
        self.assertEqual(config["exporters"][MODULE.EXPORTER_NAME]["endpoint"], "otel:4318")

    def test_build_config_reuses_existing_exporter(self):
        with mock.patch.dict(MODULE.os.environ, {}, clear=False):
            raw = MODULE.build_config(["/var/log/syslog"], "otel:4318", True)

        config = json.loads(raw)
        self.assertNotIn("exporters", config)


if __name__ == "__main__":
    unittest.main()
