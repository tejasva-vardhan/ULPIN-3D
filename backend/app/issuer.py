from __future__ import annotations

import re

NAMESPACE = "IN-ULPIN3D"
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def assert_parent_ulpin(parent_ulpin: str | None) -> str:
    if not parent_ulpin or not str(parent_ulpin).strip():
        raise ValueError("parent_ulpin is required; official 14-char ULPIN must not be invented silently")
    parent = str(parent_ulpin).strip()
    upper = parent.upper().replace(" ", "")
    if "ISO-8000" in upper or "ISO8000" in upper or "8000-118" in upper:
        raise ValueError("ISO 8000-118 is a location index, not a cadastral ULPIN. Refusing.")
    if _UUID.fullmatch(parent):
        raise ValueError("UUID is the internal primary key, not a cadastral / ULPIN display identifier")
    if len(parent) != 14:
        raise ValueError("parent_ulpin must be 14 characters (official ULPIN or labelled placeholder)")
    return parent


def issue_display_id(parent_ulpin: str, su_class: str, local_code: str, version: int = 1) -> str:
    parent = assert_parent_ulpin(parent_ulpin)
    if not local_code or str(local_code).strip() in ("", "-"):
        raise ValueError("local_code is required; UUID-only display is not allowed")
    return f"{NAMESPACE}/{parent}/{su_class}/{local_code}/v{version:02d}"

