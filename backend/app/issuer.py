from __future__ import annotations


NAMESPACE = "IN-ULPIN3D"


def issue_display_id(parent_ulpin: str, su_class: str, local_code: str, version: int = 1) -> str:
    if not parent_ulpin or not str(parent_ulpin).strip():
        raise ValueError("parent_ulpin is required; official 14-char ULPIN must not be invented silently")
    if len(parent_ulpin) != 14:
        raise ValueError("parent_ulpin must be 14 characters (official ULPIN or labelled placeholder)")
    return f"{NAMESPACE}/{parent_ulpin}/{su_class}/{local_code}/v{version:02d}"
