"""Image failure receipts disclose only fixed labels and numeric test outcomes."""

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "j03_runtime", Path(__file__).resolve().parents[1] / "j03_runtime.py"
)
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class RuntimeDiagnosticTests(unittest.TestCase):
    def test_missing_library_is_identified_without_echoing_captured_secrets(self):
        result = subprocess.CompletedProcess(
            [],
            2,
            stdout="E ImportError: libstdc++.so.6: cannot open shared object file\n"
            "1 error in 1.2s\ncredential.synthetic-secret-must-not-escape",
            stderr="Bearer synthetic-authorization-must-not-escape",
        )
        self.assertEqual(
            runtime.suite_diagnostics(result),
            {
                "exit_code": 2,
                "counts": {"error": 1},
                "missing_native_libraries": ["libstdc++.so.6"],
                "failed_groups": [],
            },
        )

    def test_unknown_failure_does_not_echo_arbitrary_test_output(self):
        result = subprocess.CompletedProcess(
            [],
            1,
            stdout="1 failed, 83 passed\nplaintext synthetic credential\n"
            "FAILED tests/unit/test_rag_parsers.py::test_sensitive_canary",
            stderr="unknown-library.so: cannot open shared object file",
        )
        safe = runtime.suite_diagnostics(result)
        self.assertEqual(
            safe,
            {
                "exit_code": 1,
                "counts": {"failed": 1, "passed": 83},
                "missing_native_libraries": [],
                "failed_groups": ["tests/unit/test_rag_parsers.py"],
            },
        )
        self.assertNotIn("credential", json.dumps(safe))


if __name__ == "__main__":
    unittest.main()
