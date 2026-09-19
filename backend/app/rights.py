"""Record rights, restrictions and responsibilities against spatial units.

Reuses the existing party / baunit / rrr tables (LADM RRR-style). Ownership
share limits (sum <= 1) apply only to RIGHT records sharing the same spatial
unit (an "ownership group"); RESTRICTION and RESPONSIBILITY records are not
share-limited, per SIH26011 task 5 scope. claim_status distinguishes an
entered claim (default) from a verified legal title; this prototype never
performs its own legal verification.
"""
from __future__ import annotations

import math
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.geo import CrsError
from app.ingest import ImportConflict
from app.record import resolve_unit_id

PARTY_TYPES = {"person", "organisation", "association", "authority"}
RRR_TYPES = {"RIGHT", "RESTRICTION", "RESPONSIBILITY"}
CLAIM_STATUSES = {"CLAIMED", "VERIFIED"}


def _as_uuid(value, field: str) -> UUID:
    if not value:
        raise CrsError(f"{field} is required")
    try:
        return UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise CrsError(f"{field} must be a UUID") from exc


def _optional_str(payload: dict, field: str) -> str | None:
    value = payload.get(field)
    if value is not None and not isinstance(value, str):
        raise CrsError(f"{field} must be a string")
    return value


def create_party(db: Session, payload: dict) -> dict:
    party_type = payload.get("party_type")
    name = payload.get("name")
    if not isinstance(party_type, str) or party_type not in PARTY_TYPES:
        raise CrsError("party_type must be one of " + ", ".join(sorted(PARTY_TYPES)))
    if not isinstance(name, str) or not name.strip():
        raise CrsError("party name is required")
    ext_ref = _optional_str(payload, "ext_ref")
    row = db.execute(text("""
        INSERT INTO party (party_type, name, ext_ref)
        VALUES (:party_type, :name, :ext_ref)
        RETURNING id::text AS id, party_type, name, ext_ref
    """), {"party_type": party_type, "name": name.strip(), "ext_ref": ext_ref}).mappings().one()
    return dict(row)


def create_baunit(db: Session, payload: dict) -> dict:
    name = _optional_str(payload, "name")
    uid = _optional_str(payload, "uid")
    try:
        row = db.execute(text("""
            INSERT INTO baunit (name, uid) VALUES (:name, :uid)
            RETURNING id::text AS id, name, uid
        """), {"name": name, "uid": uid}).mappings().one()
    except IntegrityError as exc:
        raise ImportConflict("baunit uid already exists") from exc
    return dict(row)


def link_baunit(db: Session, baunit_id, payload: dict) -> dict:
    baunit_id = _as_uuid(baunit_id, "baunit_id")
    exists = db.execute(text("SELECT 1 FROM baunit WHERE id = :id"), {"id": baunit_id}).scalar()
    if not exists:
        raise CrsError("baunit_id does not identify an existing administrative unit")
    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
    unit_id = resolve_unit_id(db, payload)
    row = db.execute(text("""
        SELECT baunit_id, local_code, display_id, status FROM spatial_unit WHERE id = :id FOR UPDATE
    """), {"id": unit_id}).mappings().one()
    if row["status"] != "ACTIVE":
        raise CrsError("administrative links can only change on ACTIVE versions")
    if db.execute(text("SELECT 1 FROM rrr WHERE spatial_unit_id=:id AND baunit_id<>:b LIMIT 1"),
                  {"id":unit_id, "b":baunit_id}).scalar():
        raise ImportConflict("existing rights reference a different administrative unit")
    if row["baunit_id"] is not None and str(row["baunit_id"]) != str(baunit_id):
        raise ImportConflict("spatial unit is already linked to a different administrative unit")
    db.execute(text("UPDATE spatial_unit SET baunit_id = :b WHERE id = :id"),
               {"b": baunit_id, "id": unit_id})
    return {"spatial_unit_id": str(unit_id), "local_code": row["local_code"],
            "baunit_id": str(baunit_id), "linked": True}


def create_rrr(db: Session, payload: dict) -> dict:
    baunit_id = _as_uuid(payload.get("baunit_id"), "baunit_id")
    party_id = _as_uuid(payload.get("party_id"), "party_id")
    rrr_type = payload.get("rrr_type")
    if not isinstance(rrr_type, str) or rrr_type not in RRR_TYPES:
        raise CrsError("rrr_type must be one of " + ", ".join(sorted(RRR_TYPES)))
    claim_status = payload.get("claim_status", "CLAIMED")
    if not isinstance(claim_status, str) or claim_status not in CLAIM_STATUSES:
        raise CrsError("claim_status must be CLAIMED or VERIFIED")
    description = _optional_str(payload, "description")
    evidence_ref = _optional_str(payload, "evidence_ref")

    if claim_status == "VERIFIED" and (not evidence_ref or not evidence_ref.strip()):
        raise CrsError("operator-asserted VERIFIED claims require evidence_ref")
    share = payload.get("share")
    if share is not None:
        if isinstance(share, bool) or not isinstance(share, (int, float)) or not math.isfinite(share):
            raise CrsError("share must be a finite number")
        share = Decimal(str(share))
        if rrr_type == "RIGHT" and (share <= 0 or share > 1):
            raise CrsError("a RIGHT share must be greater than 0 and at most 1")

    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))

    unit_id = resolve_unit_id(db, payload)
    if unit_id is None:
        raise CrsError("spatial_unit_id, or site_id and local_code, is required")

    if not db.execute(text("SELECT 1 FROM party WHERE id = :id"), {"id": party_id}).scalar():
        raise CrsError("party_id does not identify an existing party")
    if not db.execute(text("SELECT 1 FROM baunit WHERE id = :id"), {"id": baunit_id}).scalar():
        raise CrsError("baunit_id does not identify an existing administrative unit")

    unit = db.execute(text("""
        SELECT baunit_id, site_id, status, local_code FROM spatial_unit WHERE id = :id FOR UPDATE
    """), {"id": unit_id}).mappings().one()
    if unit["status"] != "ACTIVE":
        raise CrsError("rights can only be recorded against the ACTIVE version of a spatial unit")
    if unit["baunit_id"] is not None and str(unit["baunit_id"]) != str(baunit_id):
        raise ImportConflict(
            "baunit_id does not match the administrative unit already linked to this spatial unit"
        )

    if rrr_type == "RIGHT" and share is not None:
        existing_total = db.execute(text("""
            SELECT COALESCE(SUM(share), 0) FROM rrr
            WHERE spatial_unit_id = :id AND rrr_type = 'RIGHT' AND share IS NOT NULL
        """), {"id": unit_id}).scalar_one()
        if Decimal(str(existing_total)) + share > 1:
            raise ImportConflict(
                "recording this RIGHT share would push the ownership group above 1 "
                f"(existing {existing_total}, requested {share})"
            )

    try:
        row = db.execute(text("""
            INSERT INTO rrr (baunit_id, party_id, spatial_unit_id, rrr_type, share,
                              description, evidence_ref, claim_status)
            VALUES (:baunit_id, :party_id, :unit_id, :rrr_type, :share,
                    :description, :evidence_ref, :claim_status)
            RETURNING id::text AS id, baunit_id::text AS baunit_id, party_id::text AS party_id,
                      spatial_unit_id::text AS spatial_unit_id, rrr_type, share, description,
                      evidence_ref, claim_status, created_at
        """), {"baunit_id": baunit_id, "party_id": party_id, "unit_id": unit_id,
               "rrr_type": rrr_type, "share": share, "description": description,
               "evidence_ref": evidence_ref, "claim_status": claim_status}).mappings().one()
    except IntegrityError as exc:
        raise ImportConflict(
            "this baunit/party/spatial-unit/rrr_type combination is already recorded"
        ) from exc

    link_baunit(db, baunit_id, {"spatial_unit_id": unit_id})
    result = dict(row)
    if result.get("share") is not None:
        result["share"] = float(result["share"])
    result["local_code"] = unit["local_code"]
    result["not_legal_title"] = True
    result["note"] = (
        "Entered claim in the ULPIN-3D prototype. claim_status=VERIFIED still means "
        "operator-asserted, not an official legal determination."
    )
    return result


def list_rrr(db: Session, site_id=None) -> list[dict]:
    rows = db.execute(text("""
        SELECT s.local_code, s.su_class, s.site_id::text AS site_id,
               r.id::text AS id, r.baunit_id::text AS baunit_id, r.rrr_type, r.share,
               r.description, r.evidence_ref, r.claim_status, r.created_at,
               p.name AS party_name, p.party_type
        FROM rrr r
        JOIN spatial_unit s ON s.id = r.spatial_unit_id
        JOIN party p ON p.id = r.party_id
        WHERE s.status = 'ACTIVE' AND (CAST(:site AS uuid) IS NULL OR s.site_id = :site)
        ORDER BY s.local_code, r.created_at
    """), {"site": site_id}).mappings().all()
    out = []
    for r in rows:
        rec = dict(r)
        if rec.get("share") is not None:
            rec["share"] = float(rec["share"])
        out.append(rec)
    return out
