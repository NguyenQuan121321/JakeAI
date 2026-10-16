"""Provisioning formats and unconditional retirement of published signing keys."""

import base64
import binascii
import hashlib
import re

# Reviewed J01 security.py invariant, ported independently without its other work.
RETIRED_SIGNING_KEY_SHA256 = frozenset(
    (
        "012139cca3d51efe0c377b3694d80297d4e4e6f645605d5bf0a6d96461207bc5",
        "2967b9341fb99ae06ae2824ae41273b9d527820627ecd440cb7133292ec2dc56",
    )
)


def signing_key_is_retired(value: str) -> bool:
    canonical = value.lower() if re.fullmatch(r"[0-9a-fA-F]{64}", value) else value
    return hashlib.sha256(canonical.encode()).hexdigest() in RETIRED_SIGNING_KEY_SHA256


def decode_secret(value: str, *, encoding: str) -> bytes:
    """Accept canonical 32-byte provisioned material; never hash a passphrase."""
    try:
        if encoding == "hex":
            if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
                raise ValueError
            raw = bytes.fromhex(value)
        else:
            raw = base64.b64decode(value, validate=True)
            if base64.b64encode(raw).decode() != value:
                raise ValueError
        if len(raw) != 32 or len(set(raw)) < 16:
            raise ValueError
        return raw
    except (ValueError, binascii.Error):
        raise ValueError(
            "Secret must contain independently provisioned 32-byte material"
        ) from None


def validate_key_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) or value.lower().startswith(
        ("replace-", "placeholder", "changeme")
    ):
        raise ValueError("Encryption key ID must be explicitly provisioned")
    return value
