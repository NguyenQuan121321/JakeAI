"""The hosted harness must refuse local, private, foreign and wrong-branch use."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("j02_rehearsal", Path(__file__).parents[1] / "j02_rehearsal.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HostedGuards(unittest.TestCase):
    def test_local_never_reaches_docker(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(MODULE, "command") as command:
            with self.assertRaises(RuntimeError):
                MODULE.prepare()
            command.assert_not_called()

    def test_pr_repository_visibility_and_branch_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            environment = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Linux",
                "GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": "NguyenQuan121321/JakeAI",
                "GITHUB_EVENT_PATH": str(event), "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "RUNNER_TEMP": directory}
            baseline = {"repository": {"private": False}, "pull_request": {"head": {
                "repo": {"full_name": "NguyenQuan121321/JakeAI"}, "ref": "codex/j02-identity-authorization"}, "base": {"ref": "main"}}}
            for fault in ["private", "fork", "branch", "base"]:
                candidate = json.loads(json.dumps(baseline))
                if fault == "private": candidate["repository"]["private"] = True
                if fault == "fork": candidate["pull_request"]["head"]["repo"]["full_name"] = "foreign/JakeAI"
                if fault == "branch": candidate["pull_request"]["head"]["ref"] = "main"
                if fault == "base": candidate["pull_request"]["base"]["ref"] = "production"
                event.write_text(json.dumps(candidate))
                with self.subTest(fault=fault), patch.dict(os.environ, environment, clear=True), patch.object(MODULE, "command") as command:
                    with self.assertRaises(RuntimeError): MODULE.prepare()
                    command.assert_not_called()
            event.write_text(json.dumps(baseline))
            with patch.dict(os.environ, environment, clear=True):
                project, runtime = MODULE.identity()
                self.assertEqual(project, "j02-123-1")
                self.assertEqual(runtime.parent, Path(directory).resolve())


if __name__ == "__main__":
    unittest.main()
