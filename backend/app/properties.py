"""Construct property prisms from explicitly attributed GeoJSON features."""

import hashlib
import json
import math
import re
import uuid

from shapely.geometry import shape
from sqlalchemy import text

from app.geo import CrsError
from app.ingest import ImportConflict, ORIGINS
from app.solids import extrude_units
from app.validate import run_validation
from app.pipeline.utilities import utility_prism

PARENTS = {
    "PARCEL": set(), "BUILDING": {"PARCEL"}, "FLOOR": {"BUILDING"},
    "UNIT": {"BUILDING", "FLOOR"}, "COMMON": {"BUILDING", "FLOOR"},
    "PARKING": {"PARCEL", "BUILDING", "FLOOR"}, "BALCONY": {"BUILDING", "FLOOR"},
    "AIR": {"PARCEL", "BUILDING"}, "SUBSURFACE": {"PARCEL", "BUILDING", "FLOOR"},
    "UTILITY": {"PARCEL"},
}
CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


def property_features(features: list[dict], default_origin: str | None) -> list[dict]:
    rows = []
    codes = set()
    for index, feature in enumerate(features):
        props = feature["properties"]
        code = props.get("local_code")
        cls = props.get("su_class")
        parent = props.get("parent_code")
        if not isinstance(code, str) or not CODE.fullmatch(code):
            raise CrsError(f"feature {index}: local_code must be a short identifier without spaces or slashes")
        if code in codes:
            raise CrsError(f"duplicate local_code in dataset: {code}")
        codes.add(code)
        if not isinstance(cls, str) or cls not in PARENTS:
            raise CrsError(f"{code}: unsupported or missing su_class")
        if cls == "PARCEL":
            if parent is not None:
                raise CrsError(f"{code}: PARCEL must not have parent_code")
        elif not isinstance(parent, str) or not CODE.fullmatch(parent):
            raise CrsError(f"{code}: parent_code is required")
        geom = shape(feature["geometry"])
        construction = {}
        if cls == "UTILITY" and geom.geom_type == "LineString":
            geom, zmin, zmax, construction = utility_prism(geom, props)
            props = {**props, "zmin": zmin, "zmax": zmax, "requires_review": True}
        if geom.geom_type != "Polygon" or geom.has_z or geom.is_empty or not geom.is_valid:
            raise CrsError(f"{code}: a valid 2D Polygon is required; heights belong in zmin/zmax")
        heights = [props.get(k) for k in ("zmin", "zmax")]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in heights):
            raise CrsError(f"{code}: explicit finite zmin and zmax in LOCAL_SITE metres are required")
        zmin, zmax = heights
        if zmax <= zmin:
            raise CrsError(f"{code}: zmax must be greater than zmin")
        if not math.isfinite(zmax - zmin):
            raise CrsError(f"{code}: height range is too large")
        review = props.get("requires_review", False)
        if not isinstance(review, bool):
            raise CrsError(f"{code}: requires_review must be boolean")
        origin = props.get("geom_origin", default_origin)
        if not isinstance(origin, str) or origin not in ORIGINS:
            raise CrsError(f"{code}: geom_origin must explicitly identify the geometry source")
        confidence = props.get("confidence")
        if confidence is not None and (isinstance(confidence, bool) or
                not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
            raise CrsError(f"{code}: confidence must be between 0 and 1")
        level = props.get("level_index")
        if cls == "FLOOR" and (isinstance(level, bool) or not isinstance(level, int)):
            raise CrsError(f"{code}: FLOOR requires an integer level_index")
        rows.append({"id": uuid.uuid4(), "index": index, "code": code, "cls": cls,
                     "parent_code": parent, "wkt": geom.wkt, "zmin": zmin, "zmax": zmax,
                     "origin": origin, "confidence": confidence, "level": level,
                     "label": str(props.get("label", level)), "construction": construction,
                     "topology_status": "DEGRADED" if review else "PENDING"})
    return rows


def process_dataset(db, dataset_id) -> dict:
    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
    source = db.execute(text("""
        SELECT d.id, d.site_id, d.z_ref, d.meta, s.parent_ulpin, s.z_ref AS site_z_ref
        FROM source_dataset d LEFT JOIN site s ON s.id = d.site_id
        WHERE d.id = :id FOR UPDATE OF d
    """), {"id": dataset_id}).mappings().first()
    if not source:
        raise CrsError("dataset not found")
    if not source["site_id"]:
        raise CrsError("Import with site_id before processing property features")
    if source["z_ref"] != "LOCAL_SITE" or source["site_z_ref"] != "LOCAL_SITE":
        raise CrsError("Property construction currently supports LOCAL_SITE metre heights only")
    if source["meta"].get("processed_unit_ids"):
        return {"dataset_id": str(dataset_id), "unit_ids": source["meta"]["processed_unit_ids"],
                "count": len(source["meta"]["processed_unit_ids"]), "extruded_solids": 0,
                "reused": True, "validation_run_id": source["meta"]["validation_run_id"]}
    features = source["meta"].get("features")
    if not features:
        raise CrsError("Dataset has no preserved features; re-import its GeoJSON")
    rows = property_features(features, source["meta"].get("geom_origin"))
    existing = db.execute(text("""
        SELECT id, local_code, su_class FROM spatial_unit WHERE site_id = :site AND status = 'ACTIVE'
    """), {"site": source["site_id"]}).mappings().all()
    parents = {r["local_code"]: {"id": r["id"], "cls": r["su_class"]} for r in existing}
    # Never silently overwrite an existing unit or invent a version on re-import.
    conflicts = db.execute(text("""
        SELECT local_code FROM spatial_unit WHERE parent_ulpin = :parent
          AND local_code = ANY(CAST(:codes AS text[]))
    """), {"parent": source["parent_ulpin"], "codes": [r["code"] for r in rows]}).scalars().all()
    if conflicts:
        raise ImportConflict("Property codes already exist; use an explicit change workflow: " + ", ".join(sorted(set(conflicts))))
    pending = list(rows)
    ordered = []
    while pending:
        ready = [r for r in pending if r["cls"] == "PARCEL" or r["parent_code"] in parents]
        if not ready:
            raise CrsError("Missing or cyclic parent_code references: " + ", ".join(r["code"] for r in pending))
        for row in ready:
            parent = parents.get(row["parent_code"])
            if parent and parent["cls"] not in PARENTS[row["cls"]]:
                raise CrsError(f"{row['code']}: {parent['cls']} is not an allowed parent for {row['cls']}")
            row["parent_id"] = parent["id"] if parent else None
            parents[row["code"]] = row
            ordered.append(row)
            pending.remove(row)
    for row in ordered:
        db.execute(text("""
            INSERT INTO spatial_unit (
                id, parent_id, parent_ulpin, su_class, local_code, display_id,
                geom_2d, zmin, zmax, geom_origin, confidence, geom_hash,
                site_id, source_dataset_id, source_feature_index, topology_status, review_required)
            VALUES (:id, :parent_id, :ulpin, :cls, :code, :display,
                ST_GeomFromText(:wkt, 32643), :zmin, :zmax, :origin, :confidence, :hash,
                :site, :source, :index, :topology_status, (CAST(:topology_status AS topology_status) = 'DEGRADED'))
        """), {**row, "ulpin": source["parent_ulpin"], "display": f"UNISSUED/{row['id']}",
               "hash": hashlib.sha256(f"{row['wkt']}|{row['zmin']}|{row['zmax']}".encode()).hexdigest(),
               "site": source["site_id"], "source": dataset_id})
        if row["cls"] == "BUILDING":
            db.execute(text("""
                INSERT INTO building (spatial_unit_id, z_ground, z_roof, extraction_method)
                VALUES (:id, :zmin, :zmax, 'imported-geojson')
            """), row)
        elif row["cls"] == "FLOOR":
            db.execute(text("""
                INSERT INTO floor (building_id, spatial_unit_id, level_index, label)
                SELECT id, :id, :level, :label FROM building WHERE spatial_unit_id = :parent_id
            """), row)
    ids = [r["id"] for r in rows]
    extruded = extrude_units(db, ids)
    validation = run_validation(db)
    result = {"dataset_id": str(dataset_id), "unit_ids": [str(uid) for uid in ids],
              "count": len(ids), "extruded_solids": extruded, "reused": False,
              "validation_run_id": validation["run_id"],
              "note": "Geometry validation does not establish rights. Proposed IDs remain unissued."}
    db.execute(text("""
        UPDATE source_dataset SET meta = meta || CAST(:result AS jsonb) WHERE id = :id
    """), {"id": dataset_id, "result": json.dumps({"processed_unit_ids": result["unit_ids"],
                 "validation_run_id": validation["run_id"],
                 "construction": {str(r["index"]): r["construction"] for r in rows if r["construction"]}})})
    return result
