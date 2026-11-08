"""Frozen pre-optimization decoder from eef6e44 identity.py:100-128.

Differential test oracle only. Never imported by application code.
"""

import json
from typing import Any


def original_unique_object(
    raw: str | bytes, names: frozenset[str] = frozenset()
) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Ambiguous JSON member")
            result[key] = value
        return result

    try:
        obj = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Invalid JSON number")
            ),
        )
    except RecursionError:
        raise ValueError("JSON nesting exceeds parser bounds") from None
    if not isinstance(obj, dict):
        raise ValueError("JSON object required")
    if any(
        key != name and key.casefold() == name.casefold()
        for key in obj
        for name in names
    ):
        raise ValueError("Ambiguous authority member")
    return obj
