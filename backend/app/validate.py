from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

RULES = (
    "CRS_STORAGE",
    "Z_RANGE",
    "SIMPLE_2D",
    "PARENT_CONTAIN",
    "BLDG_PARCEL",
    "UNIT_OVERLAP",
    "FLOOR_GAP",
    "UTIL_Z_BELOW_GROUND",
)


def run_validation(db: Session) -> dict:
    run_id = uuid.uuid4()
    db.execute(text("DELETE FROM validation_result"))
    findings: list[dict] = []

    def add(sid, code, passed, severity, detail):
        findings.append(
            {"spatial_unit_id": str(sid) if sid else None, "rule_code": code, "passed": passed, "severity": severity, "detail": detail}
        )
        db.execute(
            text(
                """
                INSERT INTO validation_result (spatial_unit_id, run_id, rule_code, passed, severity, detail)
                VALUES (:sid, :run, :code, :passed, :sev, CAST(:detail AS jsonb))
                """
            ),
            {
                "sid": sid,
                "run": run_id,
                "code": code,
                "passed": passed,
                "sev": severity,
                "detail": json.dumps(detail),
            },
        )

    rows = db.execute(
        text(
            """
            SELECT id, su_class, local_code, parent_id, zmin, zmax,
                   ST_IsValid(geom_2d) AS ok2d,
                   ST_SRID(geom_2d) AS srid
            FROM spatial_unit
            """
        )
    ).mappings().all()

    for r in rows:
        add(r["id"], "CRS_STORAGE", r["srid"] == 32643, "ERROR" if r["srid"] != 32643 else "INFO", {"srid": r["srid"]})
        z_ok = r["zmax"] > r["zmin"]
        add(r["id"], "Z_RANGE", z_ok, "ERROR" if not z_ok else "INFO", {"zmin": r["zmin"], "zmax": r["zmax"]})
        add(r["id"], "SIMPLE_2D", bool(r["ok2d"]), "ERROR" if not r["ok2d"] else "INFO", {"local_code": r["local_code"]})

    contain = db.execute(
        text(
            """
            SELECT c.id, c.local_code
            FROM spatial_unit c
            JOIN spatial_unit p ON p.id = c.parent_id
            WHERE NOT ST_CoveredBy(ST_Buffer(c.geom_2d, 0.02), ST_Buffer(p.geom_2d, 0.05))
              AND c.su_class NOT IN ('UTILITY')
            """
        )
    ).mappings().all()
    if not contain:
        add(None, "PARENT_CONTAIN", True, "INFO", {"violations": 0})
    for v in contain:
        add(v["id"], "PARENT_CONTAIN", False, "ERROR", {"local_code": v["local_code"]})

    bldg = db.execute(
        text(
            """
            SELECT b.id, b.local_code
            FROM spatial_unit b
            JOIN spatial_unit p ON p.su_class = 'PARCEL'
            WHERE b.su_class = 'BUILDING'
              AND NOT ST_CoveredBy(ST_Buffer(b.geom_2d, 0.02), ST_Buffer(p.geom_2d, 0.05))
            """
        )
    ).mappings().all()
    if not bldg:
        add(None, "BLDG_PARCEL", True, "INFO", {"violations": 0})
    for v in bldg:
        add(v["id"], "BLDG_PARCEL", False, "ERROR", {"local_code": v["local_code"]})

    overlaps = db.execute(
        text(
            """
            SELECT a.id AS aid, a.local_code AS a, b.id AS bid, b.local_code AS b
            FROM spatial_unit a
            JOIN spatial_unit b ON a.id < b.id
            WHERE a.su_class = 'UNIT' AND b.su_class = 'UNIT'
              AND ST_Intersects(a.geom_2d, b.geom_2d)
              AND ST_Area(ST_Intersection(a.geom_2d, b.geom_2d)) > 0.05
              AND a.zmin < b.zmax AND b.zmin < a.zmax
            """
        )
    ).mappings().all()
    if not overlaps:
        add(None, "UNIT_OVERLAP", True, "INFO", {"hits": []})
    for hit in overlaps:
        add(hit["bid"], "UNIT_OVERLAP", False, "ERROR", {"a": hit["a"], "b": hit["b"]})
        db.execute(
            text("UPDATE spatial_unit SET topology_status = 'INVALID' WHERE id = :id"),
            {"id": hit["bid"]},
        )
        db.execute(
            text(
                """
                UPDATE spatial_unit SET topology_status = 'VALID'
                WHERE su_class = 'UNIT' AND id <> :id AND local_code NOT LIKE '%DUP%'
                """
            ),
            {"id": hit["bid"]},
        )

    floors = db.execute(
        text(
            """
            SELECT local_code, zmin, zmax
            FROM spatial_unit
            WHERE su_class = 'FLOOR'
            ORDER BY zmin
            """
        )
    ).mappings().all()
    gap_ok = True
    for i in range(1, len(floors)):
        gap = abs(floors[i]["zmin"] - floors[i - 1]["zmax"])
        if gap > 0.05:
            gap_ok = False
            add(None, "FLOOR_GAP", False, "WARN", {"between": [floors[i - 1]["local_code"], floors[i]["local_code"]], "gap_m": gap})
    if gap_ok:
        add(None, "FLOOR_GAP", True, "INFO", {"floors": len(floors)})

    util = db.execute(
        text(
            """
            SELECT id, local_code, zmax
            FROM spatial_unit
            WHERE su_class = 'UTILITY' AND zmax >= 0
            """
        )
    ).mappings().all()
    if not util:
        add(None, "UTIL_Z_BELOW_GROUND", True, "INFO", {})
    for u in util:
        add(u["id"], "UTIL_Z_BELOW_GROUND", False, "WARN", {"local_code": u["local_code"]})

    errors = sum(1 for f in findings if not f["passed"] and f["severity"] == "ERROR")
    return {
        "run_id": str(run_id),
        "rules": list(RULES),
        "error_count": errors,
        "finding_count": len(findings),
        "findings": findings,
    }
