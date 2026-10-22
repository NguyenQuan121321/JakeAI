"""The downstream-package gate fails closed on provenance and advisory changes."""

import hashlib
import importlib.util
import io
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "fastembed_compat",
    Path(__file__).resolve().parents[2] / "backend/vendor/verify_fastembed.py",
)
assert SPEC and SPEC.loader
compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compat)


class CompatibilityGateTests(unittest.TestCase):
    def setUp(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("fastembed/inference.py", b"original inference code")
            archive.writestr(compat.ORIGINAL_INFO + "LICENSE", b"upstream license")
            archive.writestr(
                compat.ORIGINAL_INFO + "METADATA",
                b"Name: fastembed\nVersion: 0.8.0\nRequires-Python: >=3.10.0\n"
                b"Requires-Dist: pillow (>=10.3,<13) ; python_version < '3.13'\n"
                b"Requires-Dist: pillow (>=11,<13) ; python_version == '3.13'\n"
                b"Requires-Dist: pillow (>=12,<13) ; python_version >= '3.14'\n\nOriginal description",
            )
        self.upstream = stream.getvalue()
        self.patched = compat.build_wheel(self.upstream)
        self.manifest = {
            "upstream_sha256": hashlib.sha256(self.upstream).hexdigest(),
            "patched_sha256": hashlib.sha256(self.patched).hexdigest(),
        }

    def test_reproducible_metadata_patch_preserves_inference_and_license(self):
        compat.verify_wheel(self.upstream, self.patched, self.manifest)
        with zipfile.ZipFile(io.BytesIO(self.patched)) as archive:
            self.assertEqual(
                archive.read("fastembed/inference.py"), b"original inference code"
            )
            self.assertEqual(
                archive.read(compat.PATCHED_INFO + "LICENSE"), b"upstream license"
            )
            metadata = archive.read(compat.PATCHED_INFO + "METADATA")
            self.assertIn(b"Requires-Dist: pillow (>=13.0.0,<14.0.0)", metadata)
            self.assertIn(b"Requires-Python: >=3.11.0", metadata)

    def test_tampered_upstream_rejected(self):
        with self.assertRaisesRegex(ValueError, "Upstream archive hash"):
            compat.verify_wheel(self.upstream + b"changed", self.patched, self.manifest)

    def test_reconstruction_is_identical_on_windows_and_unix_hosts(self):
        original = zipfile.ZipInfo
        for system in (0, 3):
            with self.subTest(zip_creator_system=system):

                class HostZipInfo(original):
                    def __init__(self, *args, _system=system, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.create_system = _system

                with patch.object(zipfile, "ZipInfo", HostZipInfo):
                    self.assertEqual(compat.build_wheel(self.upstream), self.patched)

    def test_rehashed_unauthorized_code_change_still_rejected(self):
        stream = io.BytesIO(self.patched)
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr("fastembed/additional.py", b"unapproved code")
        modified = stream.getvalue()
        self.manifest["patched_sha256"] = hashlib.sha256(modified).hexdigest()
        with self.assertRaisesRegex(ValueError, "Unapproved source"):
            compat.verify_wheel(self.upstream, modified, self.manifest)

    def test_active_advisory_rejected_without_severity_exceptions(self):
        with self.assertRaisesRegex(ValueError, "CVE-example"):
            compat.check_advisories(
                {
                    "info": {"name": "fastembed", "version": "0.8.0"},
                    "vulnerabilities": [{"id": "CVE-example"}],
                }
            )

    def test_missing_advisory_inventory_rejected(self):
        with self.assertRaises(KeyError):
            compat.check_advisories({"info": {"name": "fastembed", "version": "0.8.0"}})

    def test_clean_pinned_identity_accepted(self):
        compat.check_advisories(
            {"info": {"name": "fastembed", "version": "0.8.0"}, "vulnerabilities": []}
        )


if __name__ == "__main__":
    unittest.main()
