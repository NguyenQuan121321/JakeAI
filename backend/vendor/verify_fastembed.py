"""Reproduce and audit JakeAI's metadata-only FastEmbed compatibility release.

The unchanged pip-audit gate cannot query a local version on PyPI. This additional
gate audits its exact upstream code identity and rejects any unapproved wheel byte.
"""

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

VENDOR = Path(__file__).resolve().parent
BASE = "0.8.0"
PATCHED = "0.8.0+jakeai.1"
ORIGINAL_INFO = f"fastembed-{BASE}.dist-info/"
PATCHED_INFO = f"fastembed-{PATCHED}.dist-info/"
PYPI = f"https://pypi.org/pypi/fastembed/{BASE}/json"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_metadata(data: bytes) -> bytes:
    header, description = data.split(b"\n\n", 1)
    lines = header.decode().splitlines()
    pillow = [line for line in lines if line.startswith("Requires-Dist: pillow ")]
    if len(pillow) != 3:
        raise ValueError("Unexpected upstream Pillow dependency inventory")
    lines = [line for line in lines if line not in pillow]
    lines = [
        line.replace(f"Version: {BASE}", f"Version: {PATCHED}").replace(
            "Requires-Python: >=3.10.0", "Requires-Python: >=3.11.0"
        )
        for line in lines
    ]
    lines.append("Requires-Dist: pillow (>=13.0.0,<14.0.0)")
    notice = (
        b"JakeAI compatibility release: distribution metadata modified for Pillow 13; "
        b"all upstream runtime code, data, LICENSE and NOTICE are unchanged.\n\n"
    )
    return "\n".join(lines).encode() + b"\n\n" + notice + description


def build_wheel(upstream: bytes) -> bytes:
    """Keep every module/data/license byte; change only version/dependency metadata."""
    with zipfile.ZipFile(io.BytesIO(upstream)) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Duplicate upstream archive entries")
        files = {
            name.replace(ORIGINAL_INFO, PATCHED_INFO, 1): archive.read(name)
            for name in names
            if not name.endswith("/RECORD")
        }
    metadata = PATCHED_INFO + "METADATA"
    files[metadata] = patch_metadata(files[metadata])
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, data in sorted(files.items()):
        hashed = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
        writer.writerow([name, "sha256=" + hashed.decode(), len(data)])
    writer.writerow([PATCHED_INFO + "RECORD", "", ""])
    files[PATCHED_INFO + "RECORD"] = record.getvalue().encode()
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return result.getvalue()


def verify_wheel(upstream: bytes, patched: bytes, manifest: dict) -> None:
    if digest(upstream) != manifest["upstream_sha256"]:
        raise ValueError("Upstream archive hash mismatch")
    if digest(patched) != manifest["patched_sha256"]:
        raise ValueError("Patched archive hash mismatch")
    if build_wheel(upstream) != patched:
        raise ValueError("Unapproved source, data, license or metadata change")


def check_advisories(document: dict) -> None:
    if document["info"]["name"] != "fastembed" or document["info"]["version"] != BASE:
        raise ValueError("Advisory response does not describe the pinned upstream")
    advisories = document["vulnerabilities"]
    if not isinstance(advisories, list):
        raise TypeError("Missing upstream advisory inventory")
    active = [item["id"] for item in advisories if not item.get("withdrawn")]
    if active:
        raise ValueError("Upstream FastEmbed security advisories: " + ", ".join(active))


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--check-installed", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((VENDOR / "fastembed-provenance.json").read_text())
    document = json.loads(fetch(PYPI))
    check_advisories(document)
    published = next(
        item
        for item in document["urls"]
        if item["filename"] == manifest["upstream_filename"]
    )
    if published["digests"]["sha256"] != manifest["upstream_sha256"]:
        raise ValueError("Pinned wheel hash differs from official release metadata")
    if published["url"] != manifest["upstream_url"]:
        raise ValueError("Pinned wheel URL differs from official release metadata")
    upstream = fetch(manifest["upstream_url"])
    wheel = VENDOR / f"fastembed-{PATCHED}-py3-none-any.whl"
    patched = build_wheel(upstream) if args.rebuild else wheel.read_bytes()
    verify_wheel(upstream, patched, manifest)
    if args.check_installed:
        distribution = importlib.metadata.distribution("fastembed")
        if distribution.version != PATCHED:
            raise ValueError(
                "Installed distribution is not the verified compatibility release"
            )
        with zipfile.ZipFile(io.BytesIO(patched)) as archive:
            for name in archive.namelist():
                if not name.endswith("/RECORD") and (
                    distribution.locate_file(name).read_bytes() != archive.read(name)
                ):
                    raise ValueError(
                        "Installed FastEmbed bytes differ from verified release"
                    )
    if args.rebuild:
        wheel.write_bytes(patched)
    print(
        json.dumps(
            {
                "package": "fastembed",
                "version": PATCHED,
                "upstream": BASE,
                "patched_sha256": digest(patched),
                "source_data_licenses": "UNCHANGED",
                "upstream_advisories": 0,
                "provenance": "PASS",
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        StopIteration,
        zipfile.BadZipFile,
    ) as error:
        print("FastEmbed compatibility gate FAILED: " + str(error), file=sys.stderr)
        sys.exit(1)
