"""Plain 400 messages for requests that fail validation (REST and MCP alike).

They name only our own declared fields; a key the client made up is never echoed
back (security rules: one clear message, nothing reflected from the request)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

EXTRA_FIELD = "This request has a field it does not take. Remove it and try again."
_LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})
_FIELD_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")


def validation_detail(errors: Iterable[Mapping[str, Any]]) -> str:
    """One plain 400 message. It names only our own declared fields (the first part of
    each error's location); a key the client made up is never echoed back."""
    names: set[str] = set()
    for e in errors:
        if e.get("type") == "extra_forbidden":
            return EXTRA_FIELD
        loc = [part for part in e.get("loc") or () if part not in _LOCATIONS]
        if loc and isinstance(loc[0], str) and _FIELD_NAME.fullmatch(loc[0]):
            names.add(loc[0])
    if not names:
        return "Bad request."
    return f"Check {', '.join(sorted(names))}: the value is missing or not allowed."
