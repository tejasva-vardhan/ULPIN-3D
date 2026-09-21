from __future__ import annotations

import json
import math
import uuid
from itertools import combinations

from shapely import wkt
from sqlalchemy import text
from sqlalchemy.orm import Session

RULES = (
    "CRS_STORAGE", "Z_RANGE", "SIMPLE_2D", "PARENT_CONTAIN",
    "PARENT_Z", "PARENT_ACTIVE", "PARENT_VALID", "UNIT_OVERLAP",
    "FLOOR_GAP", "FLOOR_OVERLAP", "UTIL_Z_BELOW_GROUND",
    "AIR_OVER_BUILDING", "UTIL_UNIT_CLASH", "UTIL_STRUCTURE_CLASH",
    "UTIL_UTILITY_CLASH", "DUPLICATE_VOL", "CLOSED_3D",
    "TRANSPORT_Z_ABOVE_GROUND", "TRANSPORT_BUILDING_CLASH",
)
XY_TOLERANCE_M = 0.03
Z_TOLERANCE_M = 0.05
OVERLAP_TOLERANCE_M3 = 0.01


def evaluate_units(rows: list[dict]) -> tuple[list[dict], dict]:
    """Validate polygon + Z-range prisms, not arbitrary solids.

    Utility rights may cross parcels. Only UNIT pairs represent competing
    exclusive spaces here; containing floor/building envelopes are excluded.
    DEGRADED inputs stay blocked even when geometry passes.
    """
    findings = []
    by_id = {r["id"]: r for r in rows}
    polygons = {}
    errors = set()
    valid_z = set()

    def add(row, rule, passed, detail, severity="ERROR"):
        sid = row["id"]
        findings.append({
            "spatial_unit_id": str(sid), "rule_code": rule,
            "passed": bool(passed), "severity": "INFO" if passed else severity,
            "detail": detail,
        })
        if not passed and severity == "ERROR":
            errors.add(sid)

    for row in rows:
        sid = row["id"]
        add(row, "CRS_STORAGE", row["srid"] == 32643, {"srid": row["srid"]})
        z_ok = all(math.isfinite(row[k]) for k in ("zmin", "zmax")) and row["zmax"] > row["zmin"]
        add(row, "Z_RANGE", z_ok, {
            k: row[k] if math.isfinite(row[k]) else str(row[k]) for k in ("zmin", "zmax")
        })
        if z_ok:
            valid_z.add(sid)
        poly = wkt.loads(row["wkt"])
        ok = poly.geom_type == "Polygon" and not poly.is_empty and poly.is_valid and poly.area > 0
        add(row, "SIMPLE_2D", ok, {"local_code": row["local_code"]})
        if ok and row["srid"] == 32643:
            polygons[sid] = poly

    for row in rows:
        parent = by_id.get(row["parent_id"])
        if row["parent_id"] is None and row["su_class"] in ("PARCEL", "UTILITY"):
            continue
        add(row, "PARENT_ACTIVE", parent is not None, {"parent_id": str(row["parent_id"])})
        if parent is None:
            continue
        sid, pid = row["id"], parent["id"]
        if row["su_class"] != "UTILITY" and sid in polygons and pid in polygons:
            add(row, "PARENT_CONTAIN", polygons[pid].buffer(XY_TOLERANCE_M).covers(polygons[sid]),
                {"parent": parent["local_code"]})
        # Surface parcel Z limits are demo envelopes, not established vertical rights.
        if parent["su_class"] in ("BUILDING", "FLOOR") and sid in valid_z and pid in valid_z:
            add(row, "PARENT_Z",
                row["zmin"] >= parent["zmin"] - Z_TOLERANCE_M
                and row["zmax"] <= parent["zmax"] + Z_TOLERANCE_M,
                {"parent": parent["local_code"]})

    units = [r for r in rows if r["su_class"] == "UNIT" and r["id"] in polygons and r["id"] in valid_z]
    for a, b in combinations(units, 2):
        # LOCAL_SITE heights from separate sites do not share a vertical origin.
        if a.get("site_id") != b.get("site_id"):
            continue
        height = min(a["zmax"], b["zmax"]) - max(a["zmin"], b["zmin"])
        if height <= 0:
            continue
        volume = polygons[a["id"]].intersection(polygons[b["id"]]).area * height
        if volume > OVERLAP_TOLERANCE_M3:
            for row, other in ((a, b), (b, a)):
                add(row, "UNIT_OVERLAP", False, {"other_uuid": str(other["id"]),
                    "other": other["local_code"], "overlap_m3": volume})

    floors_by_parent = {}
    for row in rows:
        if row["su_class"] == "FLOOR" and row["id"] in valid_z:
            floors_by_parent.setdefault(row["parent_id"], []).append(row)
    for floors in floors_by_parent.values():
        floors.sort(key=lambda r: r["zmin"])
        for a, b in combinations(floors, 2):
            overlap = min(a["zmax"], b["zmax"]) - max(a["zmin"], b["zmin"])
            if overlap > Z_TOLERANCE_M:
                for row, other in ((a, b), (b, a)):
                    add(row, "FLOOR_OVERLAP", False, {"other": other["local_code"], "overlap_m": overlap})
        covered_to = floors[0]["zmax"]
        for row in floors[1:]:
            gap = row["zmin"] - covered_to
            if gap > Z_TOLERANCE_M:
                add(row, "FLOOR_GAP", False, {"gap_m": gap}, "WARN")
            covered_to = max(covered_to, row["zmax"])

    blocked = errors | {r["id"] for r in rows if r["topology_status"] == "DEGRADED"}
    while True:
        descendants = [r for r in rows if r["parent_id"] in blocked and r["id"] not in blocked]
        if not descendants:
            break
        for row in descendants:
            add(row, "PARENT_VALID", False, {"parent_id": str(row["parent_id"])})
            blocked.add(row["id"])

    for row in rows:
        if row["su_class"] == "UTILITY" and row["id"] in valid_z:
            add(row, "UTIL_Z_BELOW_GROUND", row["zmax"] < 0,
                {"zmax": row["zmax"], "z_ref": "LOCAL_SITE"}, "WARN")

    buildings = [r for r in rows if r["su_class"] == "BUILDING" and r["id"] in polygons and r["id"] in valid_z]
    for row in rows:
        if row["su_class"] != "AIR" or row["id"] not in polygons or row["id"] not in valid_z:
            continue
        ok = False
        detail = {"reason": "no BUILDING in the same site covers this air-rights slab above roof"}
        for b in buildings:
            if row.get("site_id") != b.get("site_id"):
                continue
            if polygons[b["id"]].buffer(XY_TOLERANCE_M).covers(polygons[row["id"]]) and row["zmin"] >= b["zmax"] - Z_TOLERANCE_M:
                ok = True
                detail = {"building": b["local_code"], "building_zmax": b["zmax"]}
                break
        add(row, "AIR_OVER_BUILDING", ok, detail)

    utilities = [r for r in rows if r["su_class"] == "UTILITY" and r["id"] in polygons and r["id"] in valid_z]
    exclusive = [r for r in rows if r["su_class"] == "UNIT" and r["id"] in polygons and r["id"] in valid_z]
    structures = [r for r in rows if r["su_class"] in ("BUILDING", "PARKING", "SUBSURFACE")
                  and r["id"] in polygons and r["id"] in valid_z]

    def overlap_volume(a, b):
        height = min(a["zmax"], b["zmax"]) - max(a["zmin"], b["zmin"])
        if height <= 0:
            return 0
        return polygons[a["id"]].intersection(polygons[b["id"]]).area * height

    for util in utilities:
        hits = []
        for unit in exclusive:
            if util.get("site_id") != unit.get("site_id"):
                continue
            volume = overlap_volume(util, unit)
            if volume > OVERLAP_TOLERANCE_M3:
                hits.append({"unit": unit["local_code"], "overlap_m3": volume})
        add(util, "UTIL_UNIT_CLASH", not hits, {"hits": hits}, "WARN")
        structure_hits = []
        for structure in structures:
            if util.get("site_id") != structure.get("site_id"):
                continue
            volume = overlap_volume(util, structure)
            if volume > OVERLAP_TOLERANCE_M3:
                structure_hits.append({"class": structure["su_class"],
                    "structure": structure["local_code"], "overlap_m3": volume})
        add(util, "UTIL_STRUCTURE_CLASH", not structure_hits,
            {"hits": structure_hits}, "WARN")

    utility_hits = {util["id"]: [] for util in utilities}
    for first, second in combinations(utilities, 2):
        if first.get("site_id") != second.get("site_id"):
            continue
        volume = overlap_volume(first, second)
        if volume > OVERLAP_TOLERANCE_M3:
            utility_hits[first["id"]].append({"utility": second["local_code"], "overlap_m3": volume})
            utility_hits[second["id"]].append({"utility": first["local_code"], "overlap_m3": volume})
    for util in utilities:
        hits = utility_hits[util["id"]]
        add(util, "UTIL_UTILITY_CLASH", not hits, {"hits": hits}, "WARN")

    for row in rows:
        if row["su_class"] != "TRANSPORT" or row["id"] not in valid_z:
            continue
        add(row, "TRANSPORT_Z_ABOVE_GROUND", row["zmin"] > 0,
            {"zmin": row["zmin"], "z_ref": "LOCAL_SITE"})

    transports = [r for r in rows if r["su_class"] == "TRANSPORT" and r["id"] in polygons and r["id"] in valid_z]
    for tr in transports:
        hits = []
        for b in buildings:
            if tr.get("site_id") != b.get("site_id"):
                continue
            height = min(tr["zmax"], b["zmax"]) - max(tr["zmin"], b["zmin"])
            if height <= 0:
                continue
            volume = polygons[tr["id"]].intersection(polygons[b["id"]]).area * height
            if volume > OVERLAP_TOLERANCE_M3:
                hits.append({"building": b["local_code"], "overlap_m3": volume})
        add(tr, "TRANSPORT_BUILDING_CLASH", not hits, {"hits": hits})

    hashes = {}
    for row in rows:
        digest = row.get("geom_hash")
        if not digest:
            continue
        hashes.setdefault((row.get("site_id"), row["su_class"], digest), []).append(row)
    for group in hashes.values():
        if len(group) < 2:
            continue
        codes = [r["local_code"] for r in group]
        for row in group:
            add(row, "DUPLICATE_VOL", False, {"others": [c for c in codes if c != row["local_code"]]})

    for row in rows:
        if "volume_m3" not in row:
            continue
        volume = row.get("volume_m3")
        solid_ok = bool(row.get("has_solid")) and volume is not None and math.isfinite(float(volume)) and float(volume) > 0
        add(row, "CLOSED_3D", solid_ok, {"volume_m3": None if volume is None else float(volume)})

    statuses = {
        r["id"]: ("DEGRADED" if r["topology_status"] == "DEGRADED"
                  else "INVALID" if r["id"] in errors else "VALID")
        for r in rows
    }
    return findings, statuses


def run_validation(db: Session) -> dict:
    run_id = uuid.uuid4()
    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
    rows = db.execute(text("""
        SELECT id, site_id, su_class, local_code, parent_id, zmin, zmax, topology_status,
               geom_hash, volume_m3, geom_3d IS NOT NULL AS has_solid,
               ST_AsText(geom_2d) AS wkt, ST_SRID(geom_2d) AS srid
        FROM spatial_unit WHERE status = 'ACTIVE' ORDER BY id FOR UPDATE
    """)).mappings().all()
    findings, statuses = evaluate_units(rows)
    for finding in findings:
        db.execute(text("""
            INSERT INTO validation_result (spatial_unit_id, run_id, rule_code, passed, severity, detail, created_at)
            VALUES (:sid, :run, :code, :passed, :severity, CAST(:detail AS jsonb), clock_timestamp())
        """), {"sid": finding["spatial_unit_id"], "run": run_id,
               "code": finding["rule_code"], "passed": finding["passed"],
               "severity": finding["severity"], "detail": json.dumps(finding["detail"])})
    for sid, status in statuses.items():
        db.execute(text("UPDATE spatial_unit SET topology_status = :status WHERE id = :id"),
                   {"id": sid, "status": status})
    return {
        "run_id": str(run_id), "rules": list(RULES),
        "error_count": sum(not f["passed"] and f["severity"] == "ERROR" for f in findings),
        "finding_count": len(findings), "findings": findings,
    }
