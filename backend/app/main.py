import asyncio
from pathlib import Path
from uuid import UUID, uuid4
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, Response, JSONResponse, StreamingResponse
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal, engine, ensure_schema, check_database
from app.record import (
    fetch_record,
    record_html,
    supersede_new_version,
    withdraw_unit,
    active_unit_id,
    AmbiguousUnit,
)
from app.rights import create_party, create_baunit, link_baunit, create_rrr, list_rrr
from app.review import record_review, review_history
from app.geo import CrsError, require_epsg, to_wgs_geojson
from app.citygml_export import building_lod1_citygml
from app.gltf_export import prisms_to_gltf
from app.ingest import create_site, ingest_dataset, list_datasets, list_sites, get_dataset, ImportConflict
from app.imagery import orthophoto_path, register_orthophoto
from app.survey import SurveyDeclaration, get_survey, record_survey
from app.properties import process_dataset
from app.pipeline.assets import KINDS, register_asset
from app.pipeline.workflow import BuildingRequest, process_building_sources
from app.issuer import issue_display_id
from app.pipeline.extract import extract_footprint, iou
from app.pipeline.synthetic_las import write_synthetic_las
from app.seed import degrade_without_plans, seed_demo
from app.validate import run_validation, RULES
from app.events import bind_loop, emit, subscribe, sse_pack
from shapely import wkt as shapely_wkt
import json

app = FastAPI(title="ULPIN-3D", version="0.1.0")
frontend_dir = Path('/frontend')
if not frontend_dir.exists():
    frontend_dir = Path(__file__).resolve().parents[2] / 'frontend'
if frontend_dir.exists():
    app.mount('/assets', StaticFiles(directory=frontend_dir), name='assets')
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AmbiguousUnit)
@app.exception_handler(ImportConflict)
async def conflict_response(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(CrsError)
async def input_error_response(request, exc):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.on_event("startup")
def _startup_schema():
    ensure_schema()


@app.on_event("startup")
async def _bind_event_loop():
    bind_loop(asyncio.get_running_loop())


@app.get("/")
def home():
    page = frontend_dir / 'index.html'
    if page.exists():
        return FileResponse(page)
    return {"ok": True, "hint": "frontend/index.html not mounted"}


@app.get('/demo')
def demo_page():
    return FileResponse(frontend_dir / 'demo.html')


@app.get('/parties')
def list_parties():
    with SessionLocal() as db:
        return {'parties': [dict(r) for r in db.execute(text(
            'SELECT id, name, party_type FROM party ORDER BY name, id'
        )).mappings()]}


@app.get('/baunits')
def list_baunits():
    with SessionLocal() as db:
        return {'baunits': [dict(r) for r in db.execute(text(
            'SELECT id, name, uid FROM baunit ORDER BY name, id'
        )).mappings()]}


@app.get("/health")
def health():
    with engine.connect() as conn:
        capabilities = check_database(conn)
        n = conn.execute(text("SELECT count(*) FROM spatial_unit")).scalar()
    return {"ok": True, **capabilities, "spatial_units": n}


@app.get("/capabilities")
def capabilities():
    """SIH26011 coverage. Proposed 3D ULPIN is not an official DoLR identifier."""
    return {
        "problem_id": "SIH26011",
        "title": "3D ULPIN Generation and Vertical Property Mapping System",
        "proposed_3d_ulpin": True,
        "official_3d_ulpin": False,
        "not_a_title": True,
        "live_stream": False,
        "demo_line": "Official ULPIN names the land. We name the volume.",
        "identities": {
            "surface_parcel": True,
            "multi_storey_apartments": True,
            "parking": True,
            "common_areas": True,
            "air_rights": True,
            "underground_utilities": True,
            "elevated_transport": True,
        },
        "integrations": {
            "gis_parcels_geojson": True,
            "floor_plans_geojson": True,
            "lidar_las_laz": True,
            "dsm_dtm_geotiff": True,
            "drone_orthophoto": "evidence-only GeoTIFF; no cadastral boundary inferred",
            "gnss_cors": "operator-declared RMSE on the site; no live CORS client",
        },
        "automation": {
            "building_extraction": "classical nDSM, not trained PointNet",
            "floor_segmentation": "plans win; otherwise 3.0 m DEGRADED bands",
            "vertical_delineation": "2D footprint extruded [zmin, zmax] SFCGAL prism",
            "topology_validation": list(RULES),
        },
        "note": "Prototype for one block. Dataset on the SIH portal is empty. Synthetic Kothrud demo is labelled as such.",
    }


@app.get("/events")
async def event_stream():
    """In-process activity feed for the workspace UI. Not GNSS CORS and not a legal ledger."""
    async def frames():
        async for event in subscribe():
            yield sse_pack(event)
    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/demo/seed")
def demo_seed():
    db = SessionLocal()
    try:
        result = seed_demo(db)
        db.commit()
        emit("demo.seeded", {"spatial_units": result.get("spatial_units")})
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
        emit("demo.degraded", {"whole_floor_units": len(result.get("whole_floor_units") or [])})
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
        emit("site.created", {"name": row.get("name") if isinstance(row, dict) else None})
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
    """Import GeoJSON without merging its features.

    Supply kind, geojson, epsg and site_id (from POST /sites) for construction.
    Use kind=survey-control with 2D Point features for GNSS/CORS observations;
    then attach reported accuracy with POST /datasets/{id}/survey.
    Optional filename, geom_origin and z_ref describe the source. Heights use
    LOCAL_SITE metres. Original features and properties remain retrievable.
    """
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


@app.post("/datasets/files")
async def upload_elevation(
    request: Request, site_id: UUID, kind: Literal["las", "dsm", "dtm"], filename: str,
    geom_origin: Literal["SURVEY", "PLAN", "AI_DERIVED", "SYNTHETIC", "MANUAL"],
    z_ref: Literal["LOCAL_SITE", "ORTHOMETRIC_EGM", "ELLIPSOIDAL_WGS84"],
    local_zero_m: float | None = None, epsg: int | None = None,
):
    """Upload raw LAS/LAZ or single-band GeoTIFF bytes (application/octet-stream).

    Vertical samples must be metres. LOCAL_SITE needs no offset. For other
    vertical references declare local_zero_m: local_z = source_z - local_zero_m.
    This offset does not perform geoid conversion. EPSG is read from the file
    when available; a supplied EPSG must agree with its CRS. Limit: 64 MiB by default.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in KINDS[kind]:
        raise CrsError("Filename extension does not match the selected elevation kind")
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (uuid4().hex + suffix)
    keep = False
    try:
        size = 0
        with path.open("xb") as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Upload exceeds the configured size limit; crop to the site first")
                handle.write(chunk)
        if not size:
            raise CrsError("Uploaded file is empty")
        with SessionLocal() as db:
            result = register_asset(db, path, site_id=site_id, kind=kind, filename=filename,
                geom_origin=geom_origin, z_ref=z_ref, local_zero_m=local_zero_m, epsg=epsg)
            db.commit()
        keep = not result['reused']
        return result
    finally:
        if not keep:
            path.unlink(missing_ok=True)


@app.post('/datasets/imagery')
async def upload_imagery(request: Request, site_id: UUID, filename: str,
                         epsg: int | None = None):
    """Upload a bounded, georeferenced RGB/RGBA drone GeoTIFF as source evidence."""
    if Path(filename).suffix.lower() not in {'.tif', '.tiff'}:
        raise CrsError('Drone orthophoto filename must end in .tif or .tiff')
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (uuid4().hex + Path(filename).suffix.lower())
    keep = False
    try:
        size = 0
        with path.open('xb') as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail='Upload exceeds the configured size limit; crop to the site first')
                handle.write(chunk)
        if not size:
            raise CrsError('Uploaded file is empty')
        with SessionLocal() as db:
            result = register_orthophoto(db, path, site_id=site_id,
                                         filename=filename, epsg=epsg)
            db.commit()
        keep = not result['reused']
        return result
    finally:
        if not keep:
            path.unlink(missing_ok=True)


@app.get("/datasets/{dataset_id}")
def read_dataset(dataset_id: UUID):
    with SessionLocal() as db:
        row = get_dataset(db, dataset_id)
        if not row:
            raise HTTPException(status_code=404, detail="dataset not found")
        return row


@app.get('/datasets/{dataset_id}/imagery')
def read_imagery(dataset_id: UUID):
    with SessionLocal() as db:
        path, source = orthophoto_path(db, dataset_id, settings.upload_dir)
    return FileResponse(path, media_type='image/tiff', filename=source['filename'])


@app.post('/datasets/{dataset_id}/survey')
def post_survey(dataset_id: UUID, declaration: SurveyDeclaration):
    """Attach reported GNSS/CORS accuracy and evidence reference to control points.

    This records provenance; it does not correct coordinates or certify a survey.
    """
    with SessionLocal() as db:
        result = record_survey(db, dataset_id, declaration)
        db.commit()
        return result


@app.get('/datasets/{dataset_id}/survey')
def read_survey(dataset_id: UUID):
    with SessionLocal() as db:
        result = get_survey(db, dataset_id)
        if result is None:
            raise HTTPException(status_code=404, detail='survey declaration not found')
        return result


@app.post("/datasets/{dataset_id}/process")
def process_properties(dataset_id: UUID):
    """Create prisms from an imported dataset, atomically and without issuing IDs.

    Each Polygon feature needs local_code, su_class, zmin, zmax and geom_origin
    (or dataset geom_origin). Non-parcels need parent_code; floors also need
    level_index. Parents may be in this dataset or already in the same site.
    See data/examples/property_import.geojson. Retrying reuses the created IDs.
    UTILITY LineStrings accept diameter_m and constant Z coordinates, zmin/zmax,
    or depth_m with ground_z_m; their buffered corridors always require review.
    """
    with SessionLocal() as db:
        try:
            result = process_dataset(db, dataset_id)
            db.commit()
            emit("dataset.processed", {"count": result.get("count")})
            return result
        except CrsError as exc:
            db.rollback()
            _crs_http(exc)


@app.get("/spatial-units")
def list_units(site_id: UUID | None = None):
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id::text AS uuid, parent_id::text AS parent_id, site_id::text AS site_id,
                       source_dataset_id::text AS source_dataset_id, source_feature_index,
                       display_id, su_class, local_code, parent_ulpin, version, status,
                       zmin, zmax, volume_m3, topology_status, geom_origin, confidence,
                       ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson
                FROM spatial_unit
                WHERE status = 'ACTIVE' AND (CAST(:site AS uuid) IS NULL OR site_id = :site)
                ORDER BY su_class, local_code
                """
            ), {"site": site_id}
        ).mappings().all()
        return {"count": len(rows), "units": [dict(r) for r in rows]}
    finally:
        db.close()


@app.get("/spatial-units/by-code/{local_code}")
def get_unit(local_code: str, site_id: UUID | None = None):
    db = SessionLocal()
    try:
        unit_id = active_unit_id(db, local_code, site_id)
        row = db.execute(
            text(
                """
                SELECT display_id, su_class, local_code, parent_ulpin, version, status,
                       zmin, zmax, volume_m3, topology_status, geom_origin, confidence,
                       ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson
                FROM spatial_unit
                WHERE id = :id
                ORDER BY version DESC
                LIMIT 1
                """
            ),
            {"id": unit_id},
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
def get_rrr(site_id: UUID | None = None):
    db = SessionLocal()
    try:
        rows = list_rrr(db, site_id)
        return {"count": len(rows), "rrr": rows}
    finally:
        db.close()


@app.post("/parties")
def post_party(payload: dict):
    """Create a party (person/organisation/association/authority)."""
    db = SessionLocal()
    try:
        row = create_party(db, payload)
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


@app.post("/baunits")
def post_baunit(payload: dict):
    """Create an administrative unit (LADM BAUnit) that RRR rows attach to."""
    db = SessionLocal()
    try:
        row = create_baunit(db, payload)
        db.commit()
        return row
    except CrsError as exc:
        db.rollback()
        _crs_http(exc)
    except ImportConflict:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/baunits/{baunit_id}/link")
def post_baunit_link(baunit_id: UUID, payload: dict):
    """Link an administrative unit to a spatial unit (UUID, or site_id + local_code)."""
    db = SessionLocal()
    try:
        row = link_baunit(db, baunit_id, payload)
        db.commit()
        return row
    except CrsError as exc:
        db.rollback()
        _crs_http(exc)
    except (AmbiguousUnit, ImportConflict):
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/rrr")
def post_rrr(payload: dict):
    """Record a RIGHT, RESTRICTION or RESPONSIBILITY against an ACTIVE spatial unit.

    Reference the unit by spatial_unit_id, or by site_id + local_code (site_id
    is required whenever local_code alone would be ambiguous). RIGHT shares on
    the same spatial unit may not sum above 1; RESTRICTION/RESPONSIBILITY
    shares are not limited this way. claim_status defaults to CLAIMED; this
    prototype never performs its own legal verification.
    """
    db = SessionLocal()
    try:
        row = create_rrr(db, payload)
        db.commit()
        emit("rrr.recorded", {"rrr_type": row.get("rrr_type"), "local_code": row.get("local_code")})
        return row
    except CrsError as exc:
        db.rollback()
        _crs_http(exc)
    except (AmbiguousUnit, ImportConflict):
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/spatial-units/{local_code}/review")
def post_review(local_code: str, payload: dict, site_id: UUID | None = None):
    """Record an explicit review decision for the ACTIVE version of a spatial unit.

    decision is APPROVED or REJECTED; reviewer_label is required prototype
    metadata, not an authenticated identity. Approval never sets topology to
    VALID by itself: pass release_review_block=true on an APPROVED decision to
    clear this unit's DEGRADED block and rerun deterministic validation, which
    alone decides VALID/INVALID. Rejection, geometry errors or unreviewed
    ancestors still block issuance.
    """
    db = SessionLocal()
    try:
        merged = {**payload, "local_code": local_code, "site_id": site_id}
        row = record_review(db, merged)
        db.commit()
        emit("unit.reviewed", {
            "local_code": row.get("local_code"),
            "decision": row.get("decision"),
            "topology_status": row.get("topology_status"),
        })
        return row
    except CrsError as exc:
        db.rollback()
        _crs_http(exc)
    except AmbiguousUnit:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/spatial-units/{local_code}/review-history")
def get_review_history(local_code: str, site_id: UUID | None = None):
    """Review history for the ACTIVE version. Use GET /reviews/{uuid} for older versions."""
    db = SessionLocal()
    try:
        return review_history(db, {"local_code": local_code, "site_id": site_id})
    except CrsError as exc:
        _crs_http(exc)
    except AmbiguousUnit:
        raise
    finally:
        db.close()


@app.get("/reviews/{spatial_unit_id}")
def get_reviews_by_unit(spatial_unit_id: UUID):
    """Review history for any specific spatial_unit version, including superseded/withdrawn ones."""
    db = SessionLocal()
    try:
        return review_history(db, {"spatial_unit_id": spatial_unit_id})
    except CrsError as exc:
        _crs_http(exc)
    finally:
        db.close()


@app.post("/units/{local_code}/withdraw")
def post_withdraw(local_code: str, payload: dict, site_id: UUID | None = None):
    """Withdraw the ACTIVE version (status -> EXTINGUISHED) with a reason. Never deletes rows."""
    db = SessionLocal()
    try:
        result = withdraw_unit(db, local_code, site_id, payload.get("reason"), payload.get("actor_label"))
        db.commit()
        emit("unit.withdrawn", {"local_code": result.get("local_code")})
        return result
    except CrsError as exc:
        db.rollback()
        _crs_http(exc)
    except AmbiguousUnit:
        db.rollback()
        raise
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


@app.post("/issue/{local_code}")
def issue_unit(local_code: str, site_id: UUID | None = None):
    db = SessionLocal()
    try:
        run_validation(db)
        unit_id = active_unit_id(db, local_code, site_id)
        row = db.execute(
            text(
                """
                SELECT id, parent_ulpin, su_class, local_code, version,
                       display_id, topology_status
                FROM spatial_unit WHERE id = :id
                ORDER BY version DESC LIMIT 1
                """
            ),
            {"id": unit_id},
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        if row["topology_status"] != "VALID":
            # Keep the failed validation evidence even though issuance is refused.
            db.commit()
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
        emit("unit.issued", {"local_code": row["local_code"]})
        return {
            "issued": True,
            "display_id": display,
            "note": "proposed 3D ULPIN. Not an official DoLR identifier.",
        }
    except HTTPException:
        db.rollback()
        raise
    except AmbiguousUnit:
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


@app.get("/records/{spatial_unit_id}")
def get_version_record(spatial_unit_id: UUID):
    """Full record, rights and source evidence for any historical version."""
    with SessionLocal() as db:
        return fetch_record(db, spatial_unit_id=spatial_unit_id)


@app.get("/record/{local_code}")
def get_record(local_code: str, site_id: UUID | None = None):
    db = SessionLocal()
    try:
        ensure_schema()
        rec = fetch_record(db, local_code, site_id)
        if not rec:
            raise HTTPException(status_code=404, detail="not found")
        return rec
    finally:
        db.close()


@app.get("/record/{local_code}/html")
def get_record_html(local_code: str, site_id: UUID | None = None):
    db = SessionLocal()
    try:
        ensure_schema()
        rec = fetch_record(db, local_code, site_id)
        if not rec:
            raise HTTPException(status_code=404, detail="not found")
        return HTMLResponse(record_html(rec))
    finally:
        db.close()


@app.get("/spatial-units/by-code/{local_code}/versions")
def list_unit_versions(local_code: str, site_id: UUID | None = None):
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT site_id::text AS site_id, id::text AS uuid, display_id, version, status, derived_from::text AS derived_from,
                       status_reason, status_actor,
                       topology_status, valid_from, valid_to
                FROM spatial_unit
                WHERE local_code = :code AND (CAST(:site AS uuid) IS NULL OR site_id = :site)
                ORDER BY version
                """
            ),
            {"code": local_code, "site": site_id},
        ).mappings().all()
        if len({r["site_id"] for r in rows}) > 1:
            raise AmbiguousUnit("local_code is ambiguous; supply site_id")
        if not rows:
            raise HTTPException(status_code=404, detail="not found")
        return {"local_code": local_code, "count": len(rows), "versions": [dict(r) for r in rows]}
    finally:
        db.close()


@app.post("/units/{local_code}/new-version")
def new_unit_version(local_code: str, site_id: UUID | None = None):
    db = SessionLocal()
    try:
        result = supersede_new_version(db, local_code, site_id)
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
def process_building(payload: BuildingRequest):
    """Measure external elevations and persist proposals, or preserve explicit plan levels."""
    with SessionLocal() as db:
        result = process_building_sources(db, payload)
        db.commit()
        metrics = result.get("metrics") if isinstance(result, dict) else None
        method = (metrics or {}).get("method") if isinstance(metrics, dict) else None
        emit("building.processed", {"method": method})
        return result


@app.get("/runs/{run_id}")
def process_run(run_id: UUID):
    with SessionLocal() as db:
        row = db.execute(text("""
            SELECT id, stage, processor_ver, source_ids, metrics, started_at, finished_at
            FROM process_run WHERE id = :id
        """), {"id":run_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="processing run not found")
        return dict(row)


@app.post("/demo/process/building")
def process_building_demo():
    db = SessionLocal()
    try:
        demo = Path(settings.demo_dir)
        las_path = demo / "block.las"
        meta = write_synthetic_las(las_path)
        extracted = extract_footprint(las_path)
        ref = db.execute(
            text("SELECT ST_AsText(geom_2d) AS wkt FROM spatial_unit WHERE su_class='BUILDING' AND status='ACTIVE' AND site_id IS NULL LIMIT 1")
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
                WHERE spatial_unit_id = (SELECT id FROM spatial_unit WHERE su_class='BUILDING' AND status='ACTIVE' AND site_id IS NULL LIMIT 1)
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
        emit("building.processed", {"method": extracted.get("method")})
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
        emit("validation.run", {"error_count": result.get("error_count")})
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


@app.get("/validation/{run_id}")
def validation_run(run_id: UUID):
    with SessionLocal() as db:
        rows = db.execute(text("""
            SELECT run_id, rule_code, passed, severity, detail, spatial_unit_id
            FROM validation_result WHERE run_id = :run_id ORDER BY passed, rule_code
        """), {"run_id": run_id}).mappings().all()
        if not rows:
            raise HTTPException(status_code=404, detail="validation run not found")
        return {"count": len(rows), "results": [dict(row) for row in rows]}


@app.get("/model.gltf")
def model_gltf():
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT local_code, zmin, zmax, ST_AsText(geom_2d) AS wkt
                FROM spatial_unit
                WHERE su_class IN ('UNIT','COMMON','PARKING','BALCONY','AIR','SUBSURFACE','UTILITY','TRANSPORT')
                  AND status = 'ACTIVE'
                  AND topology_status = 'VALID'
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
def export_citygml(site_id: UUID | None = None, building_id: UUID | None = None):
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                SELECT local_code, display_id, parent_ulpin, geom_origin,
                       zmin, zmax, ST_AsText(geom_2d) AS wkt
                FROM spatial_unit WHERE su_class = 'BUILDING' AND status = 'ACTIVE'
                AND (CAST(:site AS uuid) IS NULL OR site_id=:site)
                  AND (CAST(:building AS uuid) IS NULL OR id=:building)
                ORDER BY local_code LIMIT 1
                """
            ), {"site":site_id, "building":building_id}
        ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="No active building matches this selection")
        xml = building_lod1_citygml(dict(row))
        return Response(
            content=xml.encode("utf-8"),
            media_type="application/gml+xml",
            headers={
                "Content-Disposition": 'attachment; filename="ulpin3d-building-lod1.gml"',
                "X-ULPIN3D-Note": "physical CityGML LOD1; not legal title; proposed 3D ULPIN is not official",
            },
        )
    finally:
        db.close()


@app.get("/export/geojson")
def export_geojson(site_id: UUID | None = None):
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id::text AS uuid, site_id::text AS site_id, display_id, su_class, local_code, parent_ulpin,
                       zmin, zmax, volume_m3, topology_status, geom_origin, confidence,
                       ST_AsGeoJSON(ST_Transform(geom_2d, 4326)) AS geojson
                FROM spatial_unit
                WHERE topology_status = 'VALID' AND status = 'ACTIVE'
                  AND (CAST(:site AS uuid) IS NULL OR site_id=:site)
                ORDER BY su_class, local_code
                """
            ), {"site":site_id}
        ).mappings().all()
        if not rows:
            raise HTTPException(status_code=404, detail="No validated properties available for this selection")
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
            "name": "ULPIN-3D validated footprints (proposed, not official)",
            "features": features,
        }
        return Response(
            content=json.dumps(body).encode("utf-8"),
            media_type="application/geo+json",
            headers={
                "Content-Disposition": 'attachment; filename="ulpin3d-validated.geojson"',
            },
        )
    finally:
        db.close()


@app.post("/demo/fix-overlap")
def fix_overlap():
    db = SessionLocal()
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
        deleted = db.execute(text("""
            UPDATE spatial_unit SET status = 'EXTINGUISHED', valid_to = now()
            WHERE local_code = 'F05-U501-DUP' AND status = 'ACTIVE' AND site_id IS NULL
            RETURNING local_code
        """)).scalars().all()
        result = run_validation(db)
        candidate = db.execute(text("""
            SELECT id, parent_ulpin, su_class, local_code, version, topology_status
            FROM spatial_unit WHERE local_code = 'F05-U501' AND status = 'ACTIVE' AND site_id IS NULL
        """)).mappings().first()
        if candidate and candidate["topology_status"] == "VALID":
            display = issue_display_id(candidate["parent_ulpin"], candidate["su_class"],
                                       candidate["local_code"], candidate["version"])
            db.execute(text("UPDATE spatial_unit SET display_id = :display WHERE id = :id"),
                       {"display": display, "id": candidate["id"]})
        db.commit()
        emit("demo.overlap_fixed", {"removed": list(deleted)})
        unit = db.execute(
            text(
                """
                SELECT display_id, topology_status, confidence, geom_origin, volume_m3
                FROM spatial_unit WHERE local_code = 'F05-U501' AND status = 'ACTIVE' AND site_id IS NULL
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

