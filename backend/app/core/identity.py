"""Exact Finn v1 trust policy. No header, role or compatibility grant expansion."""

import base64
import binascii
import hashlib
import json
import time
from typing import Any

import jwt

from app.core.secret_material import signing_key_is_retired, validate_key_id

CLAIMS = frozenset(
    [
        "contract_ver",
        "iss",
        "aud",
        "sub",
        "uid",
        "type",
        "tid",
        "exp",
        "iat",
        "nbf",
        "jti",
        "sid",
        "pwdver",
        "auth_epoch",
        "perms",
        "role",
        "email",
        "tenant_id",
        "permissions",
        "roles",
        "scopes",
        "id",
    ]
)
HEADERS = frozenset(
    [
        "alg",
        "kid",
        "typ",
        "cty",
        "crit",
        "jku",
        "jwk",
        "x5u",
        "x5c",
        "x5t",
        "x5t#S256",
        "b64",
    ]
)
ALIASES = frozenset(["tenant_id", "permissions", "roles", "scopes", "id"])
MANDATORY = frozenset(
    [
        "contract_ver",
        "iss",
        "aud",
        "sub",
        "uid",
        "type",
        "tid",
        "exp",
        "iat",
        "nbf",
        "jti",
        "sid",
        "pwdver",
        "auth_epoch",
        "perms",
    ]
)


def decode_signing_key(value: str) -> bytes:
    """Finn DecodeStrongKey: canonical base64 of >=32 diverse random bytes."""
    try:
        raw = base64.b64decode(value, validate=True)
        from app.core.secret_material import RETIRED_SIGNING_KEY_SHA256

        if (
            base64.b64encode(raw).decode() != value
            or len(raw) < 32
            or len(set(raw)) < 16
            or signing_key_is_retired(value)
            or signing_key_is_retired(raw.hex())
            or hashlib.sha256(raw).hexdigest() in RETIRED_SIGNING_KEY_SHA256
        ):
            raise ValueError
        return raw
    except (ValueError, binascii.Error):
        raise ValueError(
            "Finn signing material must be canonical provisioned base64"
        ) from None


def unique_object(
    raw: str | bytes, names: frozenset[str] = frozenset()
) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Ambiguous JSON member")
            result[key] = value
        return result

    obj = json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("Invalid JSON number")
        ),
    )
    if not isinstance(obj, dict):
        raise ValueError("JSON object required")
    if any(
        key != name and key.casefold() == name.casefold()
        for key in obj
        for name in names
    ):
        raise ValueError("Ambiguous authority member")
    return obj


def configured_keys(settings: Any) -> dict[str, bytes]:
    if (
        settings.JWT_ALGORITHM != "HS256"
        or settings.JWT_ISSUER != "finnapigo"
        or settings.JWT_AUDIENCE != "jakeai-service"
    ):
        raise ValueError("Finn HS256 issuer/audience policy required")
    validate_key_id(settings.JWT_KEY_ID)
    current = decode_signing_key(settings.JWT_SECRET_KEY)
    keys = {settings.JWT_KEY_ID: current}
    previous = settings.JWT_SECRET_PREVIOUS
    if not previous:
        if (
            settings.JWT_PREVIOUS_KEY_ID
            or settings.JWT_PREVIOUS_LAST_ISSUED_AT is not None
        ):
            raise ValueError("Incomplete signing rotation")
        return keys
    validate_key_id(settings.JWT_PREVIOUS_KEY_ID)
    old = decode_signing_key(previous)
    last = settings.JWT_PREVIOUS_LAST_ISSUED_AT
    if (
        old == current
        or settings.JWT_PREVIOUS_KEY_ID == settings.JWT_KEY_ID
        or type(last) is not int
        or last <= 0
        or last > time.time()
    ):
        raise ValueError(
            "Distinct previous key and immutable past final issuance required"
        )
    if time.time() < last + 930:
        keys[settings.JWT_PREVIOUS_KEY_ID] = old
    return keys


def verify_access(token: str, settings: Any) -> dict[str, Any]:
    if type(token) is not str:
        raise ValueError("Text access credential required")
    if len(token) > 12288:
        raise ValueError("Oversize credential")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT")
    decoded = []
    for part in parts[:2]:
        raw = jwt.utils.base64url_decode(part.encode("ascii"))
        if jwt.utils.base64url_encode(raw).decode() != part:
            raise ValueError("Noncanonical JWT segment")
        decoded.append(raw)
    header = unique_object(decoded[0], HEADERS)
    claims = unique_object(decoded[1], CLAIMS)
    if (
        header.get("alg") != "HS256"
        or type(header.get("kid")) is not str
        or any(n in header for n in HEADERS - {"alg", "kid", "typ"})
        or ("typ" in header and header["typ"] != "JWT")
    ):
        raise ValueError("Unsupported JOSE policy")
    key = configured_keys(settings).get(header["kid"])
    if key is None:
        raise ValueError("Unknown or retired key")
    signature = jwt.utils.base64url_decode(parts[2].encode("ascii"))
    if (
        hashlib.sha256(signature).hexdigest()
        == "aaf884500d7d25e5ca1504276b3f8050a82f02c3950bcb7c6456a40f7e943a34"
    ):
        raise ValueError("Retired playground token")
    jwt.decode(
        token,
        key,
        algorithms=["HS256"],
        options={
            "verify_aud": False,
            "verify_exp": False,
            "verify_iat": False,
            "verify_nbf": False,
            "verify_sub": False,
            "verify_jti": False,
        },
    )
    if not claims.keys() >= MANDATORY or ALIASES & claims.keys():
        raise ValueError("Missing or aliased identity")
    for name in ["contract_ver", "uid", "pwdver", "auth_epoch", "exp", "iat", "nbf"]:
        if (
            type(claims[name]) is not int
            or claims[name] < 0
            or claims[name] > 2**63 - 1
        ):
            raise ValueError("Integer claim required")
    if (
        claims["contract_ver"] != 1
        or claims["iss"] != "finnapigo"
        or claims["type"] != "access"
        or claims["uid"] <= 0
        or claims["sub"] != str(claims["uid"])
    ):
        raise ValueError("Invalid identity or purpose")
    for name in ("tid", "sid", "jti"):
        if type(claims[name]) is not str or not claims[name].strip():
            raise ValueError("Nonempty identifier required")
    for name in ("role", "email"):
        if name in claims and type(claims[name]) is not str:
            raise ValueError("Invalid optional typed claim")
    perms = claims["perms"]
    if type(perms) is not list or any(type(p) is not str for p in perms):
        raise ValueError("Explicit permissions array required")
    audience = claims["aud"]
    if type(audience) is str:
        audience = [audience]
    if (
        type(audience) is not list
        or any(type(a) is not str for a in audience)
        or len(audience) != 2
        or set(audience) != {"finnapigo-api", "jakeai-service"}
    ):
        raise ValueError("Unauthorized audience set")
    now = time.time()
    if (
        not 0 < claims["exp"] - claims["iat"] <= 900
        or not claims["iat"] <= claims["nbf"] <= claims["exp"]
        or claims["iat"] > now + 30
        or claims["nbf"] > now + 30
        or now >= claims["exp"] + 30
    ):
        raise ValueError("Invalid access lifetime")
    return claims
