from __future__ import annotations

import uuid
from uuid import UUID
from xml.sax.saxutils import escape

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.geo import CrsError


def ensure_derived_from(db: Session) -> None:
    db.execute(
        text(
            """
            ALTER TABLE spatial_unit
              ADD COLUMN IF NOT EXISTS derived_from uuid REFERENCES spatial_unit(id)
            """
        )
    )


class AmbiguousUnit(ValueError):
    pass


def active_unit_id(db: Session, local_code: str, site_id=None):
    ids = db.execute(text("""
        SELECT id FROM spatial_unit WHERE local_code = :code AND status = 'ACTIVE'
          AND (CAST(:site AS uuid) IS NULL OR site_id = :site)
        ORDER BY version DESC LIMIT 2
    """), {"code": local_code, "site": site_id}).scalars().all()
    if len(ids) > 1:
        raise AmbiguousUnit("local_code is ambiguous; supply site_id")
    return ids[0] if ids else None


def resolve_unit_id(db: Session, payload: dict):
    """Resolve a spatial_unit_id from an explicit UUID, or site_id + local_code.

    An explicit spatial_unit_id may reference any status (so a superseded or
    withdrawn version stays inspectable). A local_code lookup only resolves
    the ACTIVE version and is site-scoped through active_unit_id, which
    raises AmbiguousUnit rather than guessing across sites.
    """
    site_id = payload.get("site_id")
    if site_id is not None:
        try:
            site_id = UUID(str(site_id))
        except ValueError as exc:
            raise CrsError("site_id must be a UUID") from exc
    explicit = payload.get("spatial_unit_id")
    if explicit not in (None, ""):
        try:
            uid = UUID(str(explicit))
        except (ValueError, AttributeError) as exc:
            raise CrsError("spatial_unit_id must be a UUID") from exc
        exists = db.execute(text("SELECT site_id, local_code FROM spatial_unit WHERE id = :id"), {"id": uid}).mappings().first()
        if not exists:
            raise CrsError("spatial_unit_id does not identify an existing spatial unit")
        if site_id is not None and exists["site_id"] != site_id:
            raise CrsError("spatial_unit_id does not belong to site_id")
        if payload.get("local_code") is not None and payload["local_code"] != exists["local_code"]:
            raise CrsError("spatial_unit_id does not match local_code")
        return uid
    code = payload.get("local_code")
    if not isinstance(code, str) or not code.strip():
        raise CrsError("supply spatial_unit_id, or site_id and local_code")
    uid = active_unit_id(db, code, site_id)
    if uid is None:
        raise CrsError(f"no active spatial unit found for local_code {code}")
    return uid


def active_children_count(db: Session, unit_id) -> int:
    return db.execute(text("""
        SELECT count(*) FROM spatial_unit WHERE parent_id = :id AND status = 'ACTIVE'
    """), {"id": unit_id}).scalar_one()


def fetch_record(db: Session, local_code: str | None = None, site_id=None, *, spatial_unit_id=None) -> dict | None:
    unit_id = (resolve_unit_id(db, {"spatial_unit_id": spatial_unit_id, "site_id": site_id})
               if spatial_unit_id else active_unit_id(db, local_code, site_id))
    if unit_id is None:
        return None
    row = db.execute(
        text(
            """
            SELECT id::text AS uuid, parent_id::text AS parent_id, derived_from::text AS derived_from,
                   parent_ulpin, su_class, local_code, version, display_id, status,
                   status_reason, status_actor, review_required, baunit_id,
                   zmin, zmax, volume_m3, geom_origin, confidence, topology_status,
                   site_id::text AS site_id, source_dataset_id::text AS source_dataset_id,
                   source_feature_index,
                   ST_AsText(geom_2d) AS wkt_32643,
                   ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson_4326
            FROM spatial_unit
            WHERE id = :id
            """
        ),
        {"id": unit_id},
    ).mappings().first()
    if not row:
        return None
    rec = dict(row)
    if rec.get("confidence") is not None:
        rec["confidence"] = float(rec["confidence"])
    if rec.get("volume_m3") is not None:
        rec["volume_m3"] = float(rec["volume_m3"])
    rrr = db.execute(
        text(
            """
            SELECT r.id::text AS id, r.rrr_type, r.share, r.description,
                   r.evidence_ref, r.claim_status, r.created_at,
                   p.name AS party_name, p.party_type
            FROM rrr r JOIN party p ON p.id = r.party_id
            WHERE r.spatial_unit_id = :id
            ORDER BY r.created_at
            """
        ),
        {"id": rec["uuid"]},
    ).mappings().all()
    rec["rrr"] = []
    for item in rrr:
        d = dict(item)
        if d.get("share") is not None:
            d["share"] = float(d["share"])
        rec["rrr"].append(d)
    rec["reviews"] = [
        dict(r)
        for r in db.execute(
            text(
                """
                SELECT id::text AS id, decision, reviewer_label, reason, evidence_ref,
                       released_block, created_at
                FROM spatial_unit_review WHERE spatial_unit_id = :id ORDER BY created_at
                """
            ),
            {"id": rec["uuid"]},
        ).mappings().all()
    ]
    rec["source"] = None
    if rec["source_dataset_id"]:
        source = db.execute(text("""
            SELECT filename, checksum_sha256, epsg, z_ref,
                   meta->'source_geojson' AS source_geojson,
                   meta->'processing' AS processing, meta->'construction' AS construction
            FROM source_dataset WHERE id = :id
        """), {"id": rec["source_dataset_id"]}).mappings().one()
        rec["source"] = {k: v for k, v in source.items() if k != "source_geojson"}
        rec["source"]["construction"] = (source["construction"] or {}).get(str(rec["source_feature_index"]))
        raw = source["source_geojson"]
        original = raw["features"][rec["source_feature_index"]] if raw["type"] == "FeatureCollection" else raw
        rec["source"]["feature"] = original
    rec["not_official_ulpin"] = True
    rec["not_a_title"] = True
    rec["note"] = (
        "Cadastral record card for the Stratum prototype. "
        "Proposed 3D ULPIN is not an official DoLR identifier. Not a legal title."
    )
    return rec


def record_html(rec: dict) -> str:
    rows = [
        ("Internal UUID (PK)", rec["uuid"]),
        ("Proposed 3D ULPIN (display)", rec["display_id"]),
        ("Parent ULPIN (14-char, not minted here)", rec["parent_ulpin"]),
        ("Class / local / version", f"{rec['su_class']} / {rec['local_code']} / v{int(rec['version']):02d}"),
        ("Status / topology", f"{rec['status']} / {rec['topology_status']}"),
        ("Z range (LOCAL_SITE m)", f"{rec['zmin']} – {rec['zmax']}"),
        ("Volume m³", rec.get("volume_m3")),
        ("geom_origin / confidence", f"{rec['geom_origin']} / {rec['confidence']}"),
        ("Derived from UUID", rec.get("derived_from") or "—"),
        ("WKT EPSG:32643", rec.get("wkt_32643")),
    ]
    body = "".join(
        f"<tr><th>{escape(str(k))}</th><td>{escape('' if v is None else str(v))}</td></tr>"
        for k, v in rows
    )
    rrr_html = "<p class='muted'>No RRR on this space.</p>"
    if rec.get("rrr"):
        bits = "".join(
            f"<li>{escape(str(r['rrr_type']))} · {escape(str(r['party_name']))}"
            f" · {escape(str(r.get('description') or ''))}</li>"
            for r in rec["rrr"]
        )
        rrr_html = f"<ul>{bits}</ul>"
    reviews_html = "".join(
        f"<li>{escape(str(r['decision']))} · {escape(str(r['reviewer_label']))}"
        f" · {escape(str(r['created_at']))} · {escape(str(r.get('reason') or ''))}"
        f" · {escape(str(r.get('evidence_ref') or ''))}</li>" for r in rec.get('reviews', [])
    ) or "<li>No review decisions recorded.</li>"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Record card · {escape(str(rec['local_code']))}</title>
<style>
  body {{ font: 14px/1.45 Segoe UI, sans-serif; max-width: 720px; margin: 24px auto; color: #122; }}
  h1 {{ font-size: 18px; margin: 0 0 6px; }}
  .banner {{ background: #221; color: #fc6; padding: 8px 10px; border-radius: 4px; margin-bottom: 12px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccd; padding: 6px 8px; vertical-align: top; }}
  th {{ width: 34%; text-align: left; background: #f4f6f8; }}
  .muted {{ color: #567; font-size: 12px; }}
  td {{ word-break: break-all; }}
</style></head><body>
<div class="banner">PROPOSED 3D ULPIN — not an official DoLR identifier. This card is not a legal title.
Official ULPIN names the land. We name the volume.</div>
<h1>Stratum cadastral record card</h1>
<p class="muted">LADM-aligned exploration prototype. Geometry origin: {escape(str(rec["geom_origin"]))}.</p>
<table>{body}</table>
<h2>RRR</h2>
{rrr_html}
<h2>Geometry review history</h2><ul>{reviews_html}</ul>
<p class="muted">{escape(rec['note'])}</p>
</body></html>
"""


def supersede_new_version(db: Session, local_code: str, site_id=None) -> dict:
    """Legal event: new UUID + version. Parent ULPIN unchanged. Old row SUPERSEDED, never recycled.

    The new version is created UNISSUED and re-validated on its own; it never
    inherits an approval, review history or issued display_id that applied
    only to the earlier version. Versioning is refused while active
    dependent units still reference this one, rather than silently leaving
    them pointed at a superseded parent.
    """
    ensure_derived_from(db)
    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
    from app.validate import run_validation

    run_validation(db)
    unit_id = active_unit_id(db, local_code, site_id)
    old = db.execute(
        text(
            """
            SELECT id, parent_id, parent_ulpin, su_class, local_code, version,
                   display_id, topology_status, status, geom_origin, confidence, baunit_id
            FROM spatial_unit
            WHERE id = :id
            """
        ),
        {"id": unit_id},
    ).mappings().first()
    if not old:
        raise ValueError("not found")
    children = active_children_count(db, old["id"])
    if children:
        raise ValueError(
            f"cannot create a new version while {children} active dependent unit(s) still "
            "reference this one; withdraw them first"
        )
    if old["topology_status"] != "VALID":
        raise ValueError("cannot version a unit that is not topology VALID")
    new_ver = int(old["version"]) + 1
    new_id = uuid.uuid4()
    display = f"UNISSUED/{new_id}"
    db.execute(
        text(
            """
            INSERT INTO spatial_unit (
              id, parent_id, parent_ulpin, su_class, local_code, version, display_id,
              status, geom_2d, zmin, zmax, geom_3d, volume_m3, geom_origin, confidence,
              topology_status, geom_hash, baunit_id, derived_from,
              site_id, source_dataset_id, source_feature_index, review_required
            )
            SELECT :nid, parent_id, parent_ulpin, su_class, local_code, :ver, :did,
                   'ACTIVE', geom_2d, zmin, zmax, geom_3d, volume_m3, geom_origin, confidence,
                   CASE WHEN review_required THEN 'DEGRADED'::topology_status ELSE 'PENDING'::topology_status END, geom_hash, baunit_id, :old,
                   site_id, source_dataset_id, source_feature_index, review_required
            FROM spatial_unit WHERE id = :old
            """
        ),
        {"nid": new_id, "ver": new_ver, "did": display, "old": old["id"]},
    )
    db.execute(
        text(
            """
            UPDATE spatial_unit
            SET status = 'SUPERSEDED', valid_to = now(), status_reason = 'superseded by new version'
            WHERE id = :old
            """
        ),
        {"old": old["id"]},
    )
    db.execute(
        text(
            """
            INSERT INTO rrr (baunit_id, party_id, spatial_unit_id, rrr_type, share, description,
                              evidence_ref, claim_status)
            SELECT baunit_id, party_id, :nid, rrr_type, share, description, evidence_ref, claim_status
            FROM rrr WHERE spatial_unit_id = :old
            """
        ),
        {"nid": new_id, "old": old["id"]},
    )
    db.execute(text("""
        INSERT INTO building (spatial_unit_id, storeys_above, storeys_below, z_ground, z_roof, extraction_method)
        SELECT :nid, storeys_above, storeys_below, z_ground, z_roof, extraction_method
        FROM building WHERE spatial_unit_id=:old
    """), {"nid":new_id, "old":old["id"]})
    db.execute(text("""
        INSERT INTO floor (spatial_unit_id, building_id, level_index, label)
        SELECT :nid, building_id, level_index, label FROM floor WHERE spatial_unit_id=:old
    """), {"nid":new_id, "old":old["id"]})
    validation = run_validation(db)
    new_status = db.execute(
        text("SELECT topology_status FROM spatial_unit WHERE id = :id"), {"id": new_id}
    ).scalar_one()
    return {
        "superseded_uuid": str(old["id"]),
        "superseded_display": old["display_id"],
        "new_uuid": str(new_id),
        "new_display": display,
        "new_topology_status": new_status,
        "local_code": old["local_code"],
        "version": new_ver,
        "parent_ulpin": old["parent_ulpin"],
        "validation_run_id": validation["run_id"],
        "note": (
            "parent ULPIN unchanged. Old UUID not recycled. New version is UNISSUED until "
            "POST /issue/{local_code} is called explicitly; rights and prior review history "
            "remain attached to their original spatial_unit_id, not copied forward as approvals."
        ),
    }


def withdraw_unit(db: Session, local_code: str, site_id, reason, actor_label=None) -> dict:
    """Withdraw the active version: status -> EXTINGUISHED. Never deletes rows.

    Rejected while active dependent units still reference this one, so a
    withdrawal cannot silently leave children pointed at a gone parent.
    """
    if not isinstance(reason, str) or not reason.strip():
        raise CrsError("a withdrawal reason is required")
    if actor_label is not None and not isinstance(actor_label, str):
        raise CrsError("actor_label must be a string")
    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
    unit_id = active_unit_id(db, local_code, site_id)
    if unit_id is None:
        raise ValueError("not found")
    row = db.execute(
        text("""
            SELECT id, display_id, local_code, su_class FROM spatial_unit WHERE id = :id FOR UPDATE
        """),
        {"id": unit_id},
    ).mappings().one()
    children = active_children_count(db, unit_id)
    if children:
        raise ValueError(
            f"cannot withdraw while {children} active dependent unit(s) still reference this one; "
            "withdraw them first"
        )
    db.execute(
        text(
            """
            UPDATE spatial_unit
            SET status = 'EXTINGUISHED', valid_to = now(), status_reason = :reason, status_actor = :actor
            WHERE id = :id AND status = 'ACTIVE'
            """
        ),
        {"id": unit_id, "reason": reason.strip(), "actor": actor_label},
    )
    from app.validate import run_validation

    validation = run_validation(db)
    return {
        "withdrawn_uuid": str(row["id"]),
        "display_id": row["display_id"],
        "local_code": row["local_code"],
        "reason": reason.strip(),
        "actor_label": actor_label,
        "validation_run_id": validation["run_id"],
        "note": "status set to EXTINGUISHED. The row, its versions, rights and review history are preserved, not deleted.",
    }
