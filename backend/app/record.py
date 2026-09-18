from __future__ import annotations

import uuid
from xml.sax.saxutils import escape

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.issuer import issue_display_id


def ensure_derived_from(db: Session) -> None:
    db.execute(
        text(
            """
            ALTER TABLE spatial_unit
              ADD COLUMN IF NOT EXISTS derived_from uuid REFERENCES spatial_unit(id)
            """
        )
    )


def fetch_record(db: Session, local_code: str) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT id::text AS uuid, parent_id::text AS parent_id, derived_from::text AS derived_from,
                   parent_ulpin, su_class, local_code, version, display_id, status,
                   zmin, zmax, volume_m3, geom_origin, confidence, topology_status,
                   ST_AsText(geom_2d) AS wkt_32643,
                   ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson_4326
            FROM spatial_unit
            WHERE local_code = :code AND status = 'ACTIVE'
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        {"code": local_code},
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
            SELECT r.rrr_type, r.share, r.description, p.name AS party_name, p.party_type
            FROM rrr r JOIN party p ON p.id = r.party_id
            WHERE r.spatial_unit_id = :id
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
    rec["not_official_ulpin"] = True
    rec["not_a_title"] = True
    rec["note"] = (
        "Cadastral record card for the ULPIN-3D prototype. "
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
<h1>ULPIN-3D cadastral record card</h1>
<p class="muted">Synthetic Kothrud/Pune demo. LADM-aligned exploration prototype.</p>
<table>{body}</table>
<h2>RRR</h2>
{rrr_html}
<p class="muted">{escape(rec['note'])}</p>
</body></html>
"""


def supersede_new_version(db: Session, local_code: str) -> dict:
    """Legal event: new UUID + version. Parent ULPIN unchanged. Old row SUPERSEDED, never recycled."""
    ensure_derived_from(db)
    old = db.execute(
        text(
            """
            SELECT id, parent_id, parent_ulpin, su_class, local_code, version,
                   display_id, topology_status, status, geom_origin, confidence, baunit_id
            FROM spatial_unit
            WHERE local_code = :code AND status = 'ACTIVE'
            ORDER BY version DESC LIMIT 1
            """
        ),
        {"code": local_code},
    ).mappings().first()
    if not old:
        raise ValueError("not found")
    if "DUP" in str(old["local_code"]):
        raise ValueError("INVALID overlap units cannot be versioned")
    if old["topology_status"] != "VALID":
        raise ValueError("cannot version a unit that is not topology VALID")
    new_ver = int(old["version"]) + 1
    new_id = uuid.uuid4()
    display = issue_display_id(old["parent_ulpin"], old["su_class"], old["local_code"], new_ver)
    db.execute(
        text(
            """
            INSERT INTO spatial_unit (
              id, parent_id, parent_ulpin, su_class, local_code, version, display_id,
              status, geom_2d, zmin, zmax, geom_3d, volume_m3, geom_origin, confidence,
              topology_status, geom_hash, baunit_id, derived_from
            )
            SELECT :nid, parent_id, parent_ulpin, su_class, local_code, :ver, :did,
                   'ACTIVE', geom_2d, zmin, zmax, geom_3d, volume_m3, geom_origin, confidence,
                   topology_status, geom_hash, baunit_id, :old
            FROM spatial_unit WHERE id = :old
            """
        ),
        {"nid": new_id, "ver": new_ver, "did": display, "old": old["id"]},
    )
    db.execute(
        text(
            """
            UPDATE spatial_unit
            SET status = 'SUPERSEDED', valid_to = now()
            WHERE id = :old
            """
        ),
        {"old": old["id"]},
    )
    db.execute(
        text(
            """
            INSERT INTO rrr (baunit_id, party_id, spatial_unit_id, rrr_type, share, description)
            SELECT baunit_id, party_id, :nid, rrr_type, share, description
            FROM rrr WHERE spatial_unit_id = :old
            """
        ),
        {"nid": new_id, "old": old["id"]},
    )
    return {
        "superseded_uuid": str(old["id"]),
        "superseded_display": old["display_id"],
        "new_uuid": str(new_id),
        "new_display": display,
        "local_code": old["local_code"],
        "version": new_ver,
        "parent_ulpin": old["parent_ulpin"],
        "note": "parent ULPIN unchanged. Old UUID not recycled. Proposed 3D ULPIN is not official.",
    }
