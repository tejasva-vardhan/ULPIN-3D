"""Explicit human review of estimated (DEGRADED) geometry.

Review approval never sets topology directly. An explicit, supported
approval (decision=APPROVED, release_review_block=true) clears this one
spatial unit's DEGRADED block and reruns the existing deterministic
topology validation (app.validate.run_validation), which alone decides
VALID / INVALID / DEGRADED for every active unit including this one.
Rejection leaves the unit blocked. reviewer_label is user-supplied
prototype metadata, not an authenticated identity, and approval never
implies legal ownership or official certification.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.geo import CrsError
from app.record import resolve_unit_id
from app.validate import run_validation

DECISIONS = {"APPROVED", "REJECTED"}


def _optional_str(payload: dict, field: str) -> str | None:
    value = payload.get(field)
    if value is not None and not isinstance(value, str):
        raise CrsError(f"{field} must be a string")
    return value


def record_review(db: Session, payload: dict) -> dict:
    decision = payload.get("decision")
    if not isinstance(decision, str) or decision not in DECISIONS:
        raise CrsError("decision must be APPROVED or REJECTED")
    reviewer_label = payload.get("reviewer_label")
    if not isinstance(reviewer_label, str) or not reviewer_label.strip():
        raise CrsError(
            "reviewer_label is required (a user-supplied prototype label, not an authenticated identity)"
        )
    reason = _optional_str(payload, "reason")
    evidence_ref = _optional_str(payload, "evidence_ref")
    release = payload.get("release_review_block", False)
    if not isinstance(release, bool):
        raise CrsError("release_review_block must be a boolean")
    if not reason or not reason.strip():
        raise CrsError("a review reason is required")
    if release and (not evidence_ref or not evidence_ref.strip()):
        raise CrsError("supporting evidence_ref is required to release a review block")
    if release and decision != "APPROVED":
        raise CrsError("release_review_block requires decision=APPROVED")

    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
    unit_id = resolve_unit_id(db, payload)
    unit = db.execute(text("""
        SELECT id, status, topology_status, local_code FROM spatial_unit WHERE id = :id FOR UPDATE
    """), {"id": unit_id}).mappings().one()
    if unit["status"] != "ACTIVE":
        raise CrsError("only the active version of a spatial unit can be reviewed")

    if decision == "REJECTED":
        db.execute(text("UPDATE spatial_unit SET topology_status='DEGRADED', review_required=true WHERE id=:id"),
                   {"id": unit_id})

    released = False
    if decision == "APPROVED" and release and unit["topology_status"] == "DEGRADED":
        # Release only this unit's review block; run_validation recomputes everyone,
        # so unreviewed ancestors/siblings/children are unaffected and stay blocked.
        db.execute(text("UPDATE spatial_unit SET topology_status = 'PENDING', review_required=true WHERE id = :id"),
                   {"id": unit_id})
        released = True

    row = db.execute(text("""
        INSERT INTO spatial_unit_review
          (spatial_unit_id, decision, reviewer_label, reason, evidence_ref, released_block, created_at)
        VALUES (:unit_id, :decision, :reviewer_label, :reason, :evidence_ref, :released, clock_timestamp())
        RETURNING id::text AS id, spatial_unit_id::text AS spatial_unit_id, decision,
                  reviewer_label, reason, evidence_ref, released_block, created_at
    """), {"unit_id": unit_id, "decision": decision, "reviewer_label": reviewer_label.strip(),
           "reason": reason, "evidence_ref": evidence_ref, "released": released}).mappings().one()

    validation = run_validation(db) if released or decision == "REJECTED" else None

    status_row = db.execute(text("""
        SELECT topology_status, display_id FROM spatial_unit WHERE id = :id
    """), {"id": unit_id}).mappings().one()

    result = dict(row)
    result["local_code"] = unit["local_code"]
    result["topology_status"] = status_row["topology_status"]
    result["display_id"] = status_row["display_id"]
    result["validation_run_id"] = validation["run_id"] if validation else None
    result["note"] = (
        "Review approval does not itself certify topology or legal ownership; only "
        "deterministic geometry validation sets VALID, and issuance still requires it."
    )
    return result


def review_history(db: Session, payload: dict) -> dict:
    unit_id = resolve_unit_id(db, payload)
    rows = db.execute(text("""
        SELECT id::text AS id, decision, reviewer_label, reason, evidence_ref,
               released_block, created_at
        FROM spatial_unit_review WHERE spatial_unit_id = :id ORDER BY created_at
    """), {"id": unit_id}).mappings().all()
    return {"spatial_unit_id": str(unit_id), "count": len(rows), "reviews": [dict(r) for r in rows]}
