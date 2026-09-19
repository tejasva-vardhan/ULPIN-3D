from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from uuid import UUID

from pyproj import Transformer
from pyproj.exceptions import ProjError
from shapely.errors import GEOSException
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.geo import CrsError, require_epsg
from app.issuer import assert_parent_ulpin

STORAGE_EPSG = 32643
ORIGINS = {"SURVEY", "PLAN", "AI_DERIVED", "SYNTHETIC", "MANUAL"}


class ImportConflict(ValueError):
    pass


def require_parent_ulpin(parent_ulpin: str | None) -> str:
    try:
        return assert_parent_ulpin(parent_ulpin)
    except ValueError as exc:
        raise CrsError(str(exc)) from exc


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reproject(geom, source_epsg: int):
    if source_epsg == STORAGE_EPSG:
        return geom
    transformer = Transformer.from_crs(source_epsg, STORAGE_EPSG, always_xy=True)
    return shp_transform(lambda x, y, z=None: transformer.transform(x, y, z, errcheck=True), geom)


def normalize_features(geojson: dict, epsg: int) -> list[dict]:
    """Preserve feature identity/properties; never union separate property spaces."""
    if not isinstance(geojson, dict):
        raise CrsError("body is not GeoJSON")
    kind = geojson.get("type")
    features = geojson.get("features") if kind == "FeatureCollection" else [
        geojson if kind == "Feature" else {"type": "Feature", "properties": {}, "geometry": geojson}
    ]
    if not isinstance(features, list) or not features:
        raise CrsError("GeoJSON must contain at least one feature")
    normalized = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise CrsError(f"feature {index}: expected a GeoJSON Feature")
        props = feature.get("properties")
        if props is None:
            props = {}
        if not isinstance(props, dict) or not feature.get("geometry"):
            raise CrsError(f"feature {index}: geometry and object properties are required")
        try:
            geom = shape(feature["geometry"])
            if geom.is_empty or not geom.is_valid:
                raise ValueError("empty or invalid geometry")
            stored = _reproject(geom, epsg)
            if stored.is_empty or not stored.is_valid or not all(math.isfinite(x) for x in stored.bounds):
                raise ValueError("invalid transformed coordinates")
        except (ValueError, TypeError, KeyError, AttributeError, ProjError, GEOSException) as exc:
            raise CrsError(f"feature {index}: invalid geometry or coordinates ({exc})") from exc
        out = {"type": "Feature", "properties": props, "geometry": mapping(stored)}
        if "id" in feature:
            out["id"] = feature["id"]
        normalized.append(out)
    return normalized


def create_site(db: Session, payload: dict) -> dict:
    epsg = require_epsg(payload.get("source_epsg", payload.get("epsg")))
    parent = require_parent_ulpin(payload.get("parent_ulpin"))
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CrsError("site name is required")
    z_ref = payload.get("z_ref") or "LOCAL_SITE"
    if z_ref != "LOCAL_SITE":
        raise CrsError("This import path supports LOCAL_SITE heights in metres only")
    bbox = None
    gj = payload.get("bbox_geojson") or payload.get("geojson")
    if gj:
        features = normalize_features(gj, epsg)
        geom = shape(features[0]["geometry"])
        if len(features) != 1 or geom.geom_type != "Polygon" or geom.has_z:
            raise CrsError("site boundary must be one 2D Polygon")
        bbox = geom.wkt
    return dict(db.execute(text("""
        INSERT INTO site (name, storage_epsg, source_epsg, z_ref, parent_ulpin, bbox, meta)
        VALUES (:name, 32643, :epsg, :zref, :parent,
                ST_GeomFromText(:bbox, 32643), CAST(:meta AS jsonb))
        RETURNING id::text AS id, name, source_epsg, storage_epsg, parent_ulpin, z_ref
    """), {"name": name.strip(), "epsg": epsg, "zref": z_ref, "parent": parent,
           "bbox": bbox, "meta": json.dumps({"note": "parent supplied by caller; not minted or verified here"})}
    ).mappings().one())


def ingest_dataset(db: Session, payload: dict, demo_dir: Path) -> dict:
    kind = payload.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        raise CrsError("dataset kind is required")
    filename = payload.get("filename") or payload.get("path") or "upload.geojson"
    if not isinstance(filename, str):
        raise CrsError("filename must be a string")
    if filename.lower().endswith((".shp", ".shx", ".dbf", ".prj")):
        raise CrsError("Shapefile is not supported here. Send GeoJSON with an explicit EPSG.")
    geojson = payload.get("geojson")
    if geojson is None:
        path = (Path(demo_dir) / filename).resolve()
        if path.parent != Path(demo_dir).resolve():
            raise CrsError("path must stay inside the demo directory")
        try:
            geojson = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CrsError("unable to read GeoJSON from the demo directory") from exc
    epsg = require_epsg(payload.get("epsg"))
    features = normalize_features(geojson, epsg)
    origin = payload.get("geom_origin")
    if origin is not None and (not isinstance(origin, str) or origin not in ORIGINS):
        raise CrsError("geom_origin must be SURVEY, PLAN, AI_DERIVED, SYNTHETIC or MANUAL")
    site_id = payload.get("site_id")
    if site_id is not None:
        try:
            site_id = UUID(str(site_id))
        except ValueError as exc:
            raise CrsError("site_id must be a UUID") from exc
        site = db.execute(text("SELECT z_ref FROM site WHERE id = :id"), {"id": site_id}).mappings().first()
        if not site:
            raise CrsError("site_id does not identify an existing site")
        z_ref = payload.get("z_ref", site["z_ref"])
        if z_ref != site["z_ref"]:
            raise CrsError("dataset and site height references must match")
    else:
        z_ref = payload.get("z_ref") or "LOCAL_SITE"
    if z_ref != "LOCAL_SITE":
        raise CrsError("This import path supports LOCAL_SITE heights in metres only")
    try:
        raw = json.dumps(geojson, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CrsError("GeoJSON must contain finite JSON values") from exc
    checksum = _checksum(raw)
    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
    existing = db.execute(text("""
        SELECT id FROM source_dataset
        WHERE site_id IS NOT DISTINCT FROM CAST(:site AS uuid)
          AND kind = :kind AND checksum_sha256 = :checksum AND epsg = :epsg
          AND z_ref = :zref AND meta->>'geom_origin' IS NOT DISTINCT FROM CAST(:origin AS text)
    """), {"site": site_id, "kind": kind.strip(), "checksum": checksum,
           "epsg": epsg, "zref": z_ref, "origin": origin}).scalar()
    if existing:
        return {**get_dataset(db, existing), "reused": True}
    meta = {"source_epsg": epsg, "storage_epsg": STORAGE_EPSG, "geom_origin": origin,
            "source_geojson": geojson, "features": features, "feature_count": len(features)}
    row = db.execute(text("""
        INSERT INTO source_dataset (kind, filename, checksum_sha256, epsg, z_ref, site_id, meta)
        VALUES (:kind, :filename, :checksum, :epsg, :zref, :site, CAST(:meta AS jsonb))
        RETURNING id
    """), {"kind": kind.strip(), "filename": filename, "checksum": checksum, "epsg": epsg,
           "zref": z_ref, "site": site_id, "meta": json.dumps(meta, allow_nan=False)}).scalar_one()
    return {**get_dataset(db, row), "reused": False}


def get_dataset(db: Session, dataset_id) -> dict | None:
    row = db.execute(text("""
        SELECT id::text AS id, site_id::text AS site_id, kind, filename,
               checksum_sha256, epsg, z_ref, ingested_at, meta
        FROM source_dataset WHERE id = :id
    """), {"id": dataset_id}).mappings().first()
    return dict(row) if row else None


def list_sites(db: Session) -> list[dict]:
    return [dict(r) for r in db.execute(text("""
        SELECT id::text AS id, name, source_epsg, storage_epsg, parent_ulpin, z_ref
        FROM site ORDER BY name
    """)).mappings().all()]


def list_datasets(db: Session) -> list[dict]:
    return [dict(r) for r in db.execute(text("""
        SELECT id::text AS id, site_id::text AS site_id, kind, filename, epsg,
               checksum_sha256, ingested_at, meta - 'source_geojson' - 'features' AS meta
        FROM source_dataset ORDER BY ingested_at DESC
    """)).mappings().all()]
