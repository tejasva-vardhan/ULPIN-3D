from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal, engine, ensure_schema
from app.record import fetch_record, record_html, supersede_new_version
from app.geo import CrsError, require_epsg, to_wgs_geojson
from app.citygml_export import building_lod1_citygml
from app.gltf_export import prisms_to_gltf
from app.ingest import create_site, ingest_dataset, list_datasets, list_sites
from app.issuer import issue_display_id
from app.pipeline.extract import extract_footprint, iou
from app.pipeline.synthetic_las import write_synthetic_las
from app.seed import degrade_without_plans, seed_demo
from app.validate import run_validation
from shapely import wkt as shapely_wkt
import json

app = FastAPI(title="ULPIN-3D", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_schema():
    try:
        ensure_schema()
    except Exception:
        pass


@app.get("/")
def home():
    page = Path("/frontend/index.html")
    if page.exists():
        return FileResponse(page)
    return {"ok": True, "hint": "frontend/index.html not mounted"}


@app.get("/health")
def health():
    with engine.connect() as conn:
        postgis = conn.execute(text("SELECT PostGIS_Version()")).scalar()
        sfcgal = conn.execute(
            text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='postgis_sfcgal')")
        ).scalar()
        n = conn.execute(text("SELECT count(*) FROM spatial_unit")).scalar()
    return {"ok": True, "postgis": postgis, "sfcgal": bool(sfcgal), "spatial_units": n}


@app.post("/demo/seed")
def demo_seed():
    db = SessionLocal()
    try:
        result = seed_demo(db)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/demo/degraded-no-plans")
def demo_degraded():
    db = SessionLocal()
    try:
        result = degrade_without_plans(db)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _crs_http(exc: CrsError):
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/datasets/check-crs")
def check_crs(payload: dict):
    try:
        epsg = require_epsg(payload.get("epsg"))
    except CrsError as exc:
        _crs_http(exc)
    return {"ok": True, "epsg": epsg}


@app.post("/sites")
def post_site(payload: dict):
    db = SessionLocal()
    try:
        row = create_site(db, payload)
        db.commit()
        return row
    except CrsError as exc:
        db.rollback()
        _crs_http(exc)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/sites")
def get_sites():
    db = SessionLocal()
    try:
        rows = list_sites(db)
        return {"count": len(rows), "sites": rows}
    finally:
        db.close()


@app.post("/datasets")
def post_dataset(payload: dict):
    db = SessionLocal()
    try:
        row = ingest_dataset(db, payload, Path(settings.demo_dir))
        db.commit()
        return row
    except CrsError as exc:
        db.rollback()
        _crs_http(exc)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/datasets")
def get_datasets():
    db = SessionLocal()
    try:
        rows = list_datasets(db)
        return {"count": len(rows), "datasets": rows}
    finally:
        db.close()


@app.get("/spatial-units")
def list_units():
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT display_id, su_class, local_code, parent_ulpin, version, status,
                       zmin, zmax, volume_m3, topology_status, geom_origin, confidence,
                       ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson
                FROM spatial_unit
                WHERE status = 'ACTIVE'
                ORDER BY su_class, local_code
                """
            )
        ).mappings().all()
        return {"count": len(rows), "units": [dict(r) for r in rows]}
    finally:
        db.close()


@app.get("/spatial-units/by-code/{local_code}")
def get_unit(local_code: str):
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT display_id, su_class, local_code, parent_ulpin, version, status,
                       zmin, zmax, volume_m3, topology_status, geom_origin, confidence,
                       ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson
                FROM spatial_unit
                WHERE local_code = :code AND status = 'ACTIVE'
                ORDER BY version DESC
                LIMIT 1
                """
            ),
            {"code": local_code},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return dict(row)
    finally:
        db.close()


def _units_of_class(su_class: str):
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT display_id, su_class, local_code, parent_ulpin, version, status,
                       zmin, zmax, volume_m3, topology_status, geom_origin, confidence,
                       ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson
                FROM spatial_unit
                WHERE su_class = :cls AND status = 'ACTIVE'
                ORDER BY zmin, local_code
                """
            ),
            {"cls": su_class},
        ).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()


@app.get("/parcel")
def get_parcel():
    rows = _units_of_class("PARCEL")
    if not rows:
        raise HTTPException(status_code=404, detail="seed the demo first")
    return rows[0]


@app.get("/building")
def get_building():
    rows = _units_of_class("BUILDING")
    if not rows:
        raise HTTPException(status_code=404, detail="seed the demo first")
    return rows[0]


@app.get("/floors")
def get_floors():
    rows = _units_of_class("FLOOR")
    return {"count": len(rows), "floors": rows}


@app.get("/rrr")
def get_rrr():
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT s.local_code, s.su_class, r.rrr_type, r.share, r.description,
                       p.name AS party_name, p.party_type
                FROM rrr r
                JOIN spatial_unit s ON s.id = r.spatial_unit_id
                JOIN party p ON p.id = r.party_id
                WHERE s.status = 'ACTIVE'
                ORDER BY s.local_code
                """
            )
        ).mappings().all()
        out = []
        for r in rows:
            rec = dict(r)
            if rec.get("share") is not None:
                rec["share"] = float(rec["share"])
            out.append(rec)
        return {"count": len(out), "rrr": out}
    finally:
        db.close()


@app.post("/issue/{local_code}")
def issue_unit(local_code: str):
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT id, parent_ulpin, su_class, local_code, version,
                       display_id, topology_status
                FROM spatial_unit WHERE local_code = :code AND status = 'ACTIVE'
                ORDER BY version DESC LIMIT 1
                """
            ),
            {"code": local_code},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        if row["topology_status"] != "VALID":
            raise HTTPException(
                status_code=409,
                detail="cannot issue proposed 3D ULPIN while topology is not VALID",
            )
        display = issue_display_id(
            row["parent_ulpin"], row["su_class"], row["local_code"], row["version"]
        )
        db.execute(
            text("UPDATE spatial_unit SET display_id = :did WHERE id = :id"),
            {"did": display, "id": row["id"]},
        )
        db.commit()
        return {
            "issued": True,
            "display_id": display,
            "note": "proposed 3D ULPIN. Not an official DoLR identifier.",
        }
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/record/{local_code}")
def get_record(local_code: str):
    db = SessionLocal()
    try:
        ensure_schema()
        rec = fetch_record(db, local_code)
        if not rec:
            raise HTTPException(status_code=404, detail="not found")
        return rec
    finally:
        db.close()


@app.get("/record/{local_code}/html")
def get_record_html(local_code: str):
    db = SessionLocal()
    try:
        ensure_schema()
        rec = fetch_record(db, local_code)
        if not rec:
            raise HTTPException(status_code=404, detail="not found")
        return HTMLResponse(record_html(rec))
    finally:
        db.close()


@app.get("/spatial-units/by-code/{local_code}/versions")
def list_unit_versions(local_code: str):
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id::text AS uuid, display_id, version, status, derived_from::text AS derived_from,
                       topology_status, valid_from, valid_to
                FROM spatial_unit
                WHERE local_code = :code
                ORDER BY version
                """
            ),
            {"code": local_code},
        ).mappings().all()
        if not rows:
            raise HTTPException(status_code=404, detail="not found")
        return {"local_code": local_code, "count": len(rows), "versions": [dict(r) for r in rows]}
    finally:
        db.close()


@app.post("/units/{local_code}/new-version")
def new_unit_version(local_code: str):
    db = SessionLocal()
    try:
        result = supersede_new_version(db, local_code)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        msg = str(exc)
        code = 404 if msg == "not found" else 409
        raise HTTPException(status_code=code, detail=msg) from exc
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/process/building")
def process_building():
    db = SessionLocal()
    try:
        demo = Path(settings.demo_dir)
        las_path = demo / "block.las"
        meta = write_synthetic_las(las_path)
        extracted = extract_footprint(las_path)
        ref = db.execute(
            text("SELECT ST_AsText(geom_2d) AS wkt FROM spatial_unit WHERE su_class='BUILDING' AND status='ACTIVE' LIMIT 1")
        ).scalar()
        if not ref:
            raise HTTPException(status_code=400, detail="seed the demo before extracting")
        score = iou(extracted["wkt"], ref)
        used_fallback = score < 0.70
        if used_fallback:
            poly = shapely_wkt.loads(ref)
            extracted = {
                "wkt": ref,
                "area_m2": float(poly.area),
                "method": "FALLBACK_AUTHORED_PLAN",
                "geom_origin": "PLAN",
                "ndsm_iou": score,
            }
        else:
            poly = shapely_wkt.loads(extracted["wkt"])
        db.execute(
            text(
                """
                UPDATE building SET extraction_method = :m,
                  z_ground = COALESCE(z_ground, 0),
                  z_roof = COALESCE(z_roof, 15)
                WHERE spatial_unit_id = (SELECT id FROM spatial_unit WHERE su_class='BUILDING' AND status='ACTIVE' LIMIT 1)
                """
            ),
            {"m": extracted["method"]},
        )
        gj_path = demo / "extract_footprint.geojson"
        gj_path.write_text(
            json.dumps(
                {
                    "type": "Feature",
                    "properties": {
                        "geom_origin": extracted.get("geom_origin", "AI_DERIVED"),
                        "method": extracted["method"],
                        "iou_vs_authored_building": score,
                        "not_legal_title": True,
                    },
                    "geometry": to_wgs_geojson(poly),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        db.execute(
            text(
                """
                INSERT INTO process_run (stage, processor_ver, metrics, finished_at)
                VALUES ('building_extract', :ver, CAST(:m AS jsonb), now())
                """
            ),
            {
                "ver": settings.processor_ver,
                "m": json.dumps(
                    {
                        "las": meta,
                        "extract": extracted,
                        "iou": score,
                        "used_fallback": used_fallback,
                        "geojson": str(gj_path),
                    }
                ),
            },
        )
        db.commit()
        return {
            "las": meta,
            "extract": extracted,
            "geojson": to_wgs_geojson(poly),
            "iou_vs_authored_building": score,
            "used_fallback_authored_plan": used_fallback,
            "note": (
                "IoU below 0.70 so authored plan footprint was used. Still not legal title."
                if used_fallback
                else "classical nDSM extract. AI_DERIVED geometry is not cadastral/legal truth."
            ),
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/validate")
def validate():
    db = SessionLocal()
    try:
        result = run_validation(db)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/validation/latest")
def validation_latest():
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT run_id, rule_code, passed, severity, detail, spatial_unit_id
                FROM validation_result
                WHERE run_id = (SELECT run_id FROM validation_result ORDER BY created_at DESC LIMIT 1)
                ORDER BY passed, rule_code
                """
            )
        ).mappings().all()
        return {"count": len(rows), "results": [dict(r) for r in rows]}
    finally:
        db.close()


@app.get("/model.gltf")
def model_gltf():
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT local_code, zmin, zmax, ST_AsText(geom_2d) AS wkt
                FROM spatial_unit
                WHERE su_class IN ('UNIT','COMMON','PARKING','UTILITY')
                  AND status = 'ACTIVE'
                  AND local_code NOT LIKE '%DUP%'
                ORDER BY zmin, local_code
                """
            )
        ).mappings().all()
        if not rows:
            raise HTTPException(status_code=404, detail="seed the demo first")
        body = prisms_to_gltf([dict(r) for r in rows])
        return Response(content=body, media_type="model/gltf+json")
    finally:
        db.close()


@app.get("/export/citygml")
def export_citygml():
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT local_code, display_id, parent_ulpin, geom_origin,
                       zmin, zmax, ST_AsText(geom_2d) AS wkt
                FROM spatial_unit WHERE su_class = 'BUILDING' AND status = 'ACTIVE'
                ORDER BY local_code LIMIT 1
                """
            )
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="seed the demo first")
        xml = building_lod1_citygml(dict(row))
        return Response(
            content=xml.encode("utf-8"),
            media_type="application/gml+xml",
            headers={
                "Content-Disposition": 'attachment; filename="ulpin3d-kothrud-lod1.gml"',
                "X-ULPIN3D-Note": "physical CityGML LOD1; not legal title; proposed 3D ULPIN is not official",
            },
        )
    finally:
        db.close()


@app.get("/export/geojson")
def export_geojson():
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT display_id, su_class, local_code, parent_ulpin,
                       zmin, zmax, volume_m3, topology_status, geom_origin, confidence,
                       ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson
                FROM spatial_unit
                WHERE local_code NOT LIKE '%DUP%' AND status = 'ACTIVE'
                ORDER BY su_class, local_code
                """
            )
        ).mappings().all()
        if not rows:
            raise HTTPException(status_code=404, detail="seed the demo first")
        features = []
        for r in rows:
            geom = json.loads(r["geojson"]) if isinstance(r["geojson"], str) else r["geojson"]
            props = {}
            for k in r.keys():
                if k == "geojson":
                    continue
                v = r[k]
                if hasattr(v, "as_tuple"):
                    v = float(v)
                props[k] = v
            props["not_official_ulpin"] = True
            features.append({"type": "Feature", "properties": props, "geometry": geom})
        body = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            "name": "ULPIN-3D legal footprints (proposed, not official)",
            "features": features,
        }
        return Response(
            content=json.dumps(body).encode("utf-8"),
            media_type="application/geo+json",
            headers={
                "Content-Disposition": 'attachment; filename="ulpin3d-kothrud-legal.geojson"',
            },
        )
    finally:
        db.close()


@app.post("/demo/fix-overlap")
def fix_overlap():
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                DELETE FROM validation_result
                WHERE spatial_unit_id IN (SELECT id FROM spatial_unit WHERE local_code LIKE '%DUP%')
                """
            )
        )
        db.execute(
            text(
                """
                DELETE FROM rrr
                WHERE spatial_unit_id IN (SELECT id FROM spatial_unit WHERE local_code LIKE '%DUP%')
                """
            )
        )
        deleted = db.execute(
            text("DELETE FROM spatial_unit WHERE local_code LIKE '%DUP%' RETURNING local_code")
        ).scalars().all()
        result = run_validation(db)
        db.commit()
        unit = db.execute(
            text(
                """
                SELECT display_id, topology_status, confidence, geom_origin, volume_m3
                FROM spatial_unit WHERE local_code = 'F05-U501' AND status = 'ACTIVE'
                """
            )
        ).mappings().first()
        return {
            "removed": list(deleted),
            "validation": {"error_count": result["error_count"], "finding_count": result["finding_count"]},
            "flat_501": dict(unit) if unit else None,
            "note": "seeded overlap withdrawn. Proposed 3D ULPIN may issue on VALID units only.",
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

