from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shp_transform
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.geo import CrsError, require_epsg

STORAGE_EPSG = 32643


def require_parent_ulpin(parent_ulpin: str | None) -> str:
    if not parent_ulpin or not str(parent_ulpin).strip():
        raise CrsError("parent_ulpin is required; do not invent an official ULPIN")
    parent_ulpin = str(parent_ulpin).strip()
    if len(parent_ulpin) != 14:
        raise CrsError("parent_ulpin must be 14 characters (official ULPIN or labelled placeholder)")
    return parent_ulpin


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reproject(geom, source_epsg: int):
    if int(source_epsg) == STORAGE_EPSG:
        return geom
    t = Transformer.from_crs(f"EPSG:{int(source_epsg)}", f"EPSG:{STORAGE_EPSG}", always_xy=True)
    return shp_transform(lambda x, y, z=None: t.transform(x, y), geom)


def create_site(db: Session, payload: dict) -> dict:
    epsg = require_epsg(payload.get("source_epsg") if "source_epsg" in payload else payload.get("epsg"))
    parent = require_parent_ulpin(payload.get("parent_ulpin"))
    name = (payload.get("name") or "").strip()
    if not name:
        raise CrsError("site name is required")
    z_ref = payload.get("z_ref") or "LOCAL_SITE"
    bbox_wkt = None
    gj = payload.get("bbox_geojson") or payload.get("geojson")
    if gj:
        geom = _reproject(shape(gj if gj.get("type") != "Feature" else gj["geometry"]), epsg)
        bbox_wkt = geom.wkt
    params = {
        "name": name,
        "storage": STORAGE_EPSG,
        "src": epsg,
        "zref": z_ref,
        "ulpin": parent,
        "meta": json.dumps({"note": "proposed 3D ULPIN site; parent is not minted by this system"}),
    }
    if bbox_wkt:
        params["bbox"] = bbox_wkt
        sql = """
            INSERT INTO site (name, storage_epsg, source_epsg, z_ref, parent_ulpin, bbox, meta)
            VALUES (:name, :storage, :src, :zref, :ulpin, ST_SetSRID(ST_GeomFromText(:bbox), 32643), CAST(:meta AS jsonb))
            RETURNING id::text AS id, name, source_epsg, storage_epsg, parent_ulpin, z_ref
        """
    else:
        sql = """
            INSERT INTO site (name, storage_epsg, source_epsg, z_ref, parent_ulpin, bbox, meta)
            VALUES (:name, :storage, :src, :zref, :ulpin, NULL, CAST(:meta AS jsonb))
            RETURNING id::text AS id, name, source_epsg, storage_epsg, parent_ulpin, z_ref
        """
    row = db.execute(text(sql), params).mappings().first()
    return dict(row)


def ingest_dataset(db: Session, payload: dict, demo_dir: Path) -> dict:
    kind = (payload.get("kind") or "").strip()
    if not kind:
        raise CrsError("dataset kind is required")
    filename = payload.get("filename") or payload.get("path") or "upload.geojson"
    geojson = payload.get("geojson")
    if geojson is None:
        rel = payload.get("path") or payload.get("filename")
        if not rel:
            raise CrsError("geojson body or path under demo dir is required")
        path = (Path(demo_dir) / Path(str(rel)).name).resolve()
        if path.parent.resolve() != Path(demo_dir).resolve():
            raise CrsError("path must stay inside the demo directory")
        if not path.exists():
            raise CrsError(f"file not found: {path.name}")
        geojson = json.loads(path.read_text(encoding="utf-8"))
        filename = path.name

    epsg = payload.get("epsg")
    if epsg is None:
        raise CrsError("CRS missing: EPSG is required. Refusing to guess.")
    source_epsg = require_epsg(epsg)

    geom = _geom_from_geojson(geojson)
    stored = _reproject(geom, source_epsg)
    raw = json.dumps(geojson, sort_keys=True)
    row = db.execute(
        text(
            """
            INSERT INTO source_dataset (kind, filename, checksum_sha256, epsg, z_ref, meta)
            VALUES (:kind, :fn, :chk, :epsg, :zref, CAST(:meta AS jsonb))
            RETURNING id::text AS id, kind, filename, epsg, checksum_sha256
            """
        ),
        {
            "kind": kind,
            "fn": str(filename),
            "chk": _checksum(raw),
            "epsg": STORAGE_EPSG,
            "zref": payload.get("z_ref") or "LOCAL_SITE",
            "meta": json.dumps(
                {
                    "source_epsg": source_epsg,
                    "storage_epsg": STORAGE_EPSG,
                    "storage_wkt": stored.wkt,
                    "geom_type": stored.geom_type,
                    "area_m2": float(stored.area) if stored.geom_type in ("Polygon", "MultiPolygon") else None,
                    "crs_note": "reprojected to EPSG:32643 for storage; source CRS was not guessed",
                }
            ),
        },
    ).mappings().first()
    return {
        **dict(row),
        "source_epsg": source_epsg,
        "storage_epsg": STORAGE_EPSG,
        "geom_type": stored.geom_type,
        "area_m2": float(stored.area) if stored.geom_type in ("Polygon", "MultiPolygon") else None,
        "storage_wkt": stored.wkt,
    }


def _geom_from_geojson(geojson: dict):
    if not isinstance(geojson, dict) or "type" not in geojson:
        raise CrsError("body is not GeoJSON")
    t = geojson["type"]
    if t == "FeatureCollection":
        geoms = [shape(f["geometry"]) for f in geojson.get("features") or [] if f.get("geometry")]
        if not geoms:
            raise CrsError("FeatureCollection has no geometries")
        g = geoms[0]
        for extra in geoms[1:]:
            g = g.union(extra)
        return g
    if t == "Feature":
        if not geojson.get("geometry"):
            raise CrsError("Feature has no geometry")
        return shape(geojson["geometry"])
    return shape(geojson)


def list_sites(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT id::text AS id, name, source_epsg, storage_epsg, parent_ulpin, z_ref
            FROM site ORDER BY name
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def list_datasets(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT id::text AS id, kind, filename, epsg, checksum_sha256, ingested_at, meta
            FROM source_dataset ORDER BY ingested_at DESC
            """
        )
    ).mappings().all()
    return [dict(r) for r in rows]
