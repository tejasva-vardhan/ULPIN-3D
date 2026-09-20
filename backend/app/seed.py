from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from shapely.geometry import LineString, mapping
from shapely.ops import transform as shp_transform
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.geo import lonlat_to_utm, rect_from_origin, to_wgs_geojson, utm_to_lonlat
from app.issuer import issue_display_id
from app.solids import extrude_units
from app.ingest import ImportConflict

PARENT_ULPIN = "ULPIN14PLACE01"
SITE_NAME = "Kothrud demo block (synthetic)"
ORIGIN_LON = 73.80770
ORIGIN_LAT = 18.50740
STOREY_M = 3.0
FLOORS = 5
PARCEL = (0.0, 0.0, 42.0, 32.0)  # x, y, w, h in metres from origin
BUILDING = (10.0, 8.0, 22.0, 16.0)
CORRIDOR_W = 2.2


def _checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _insert_su(db: Session, **kw):
    db.execute(
        text(
            """
            INSERT INTO spatial_unit (
              id, parent_id, parent_ulpin, su_class, local_code, version, display_id,
              status, geom_2d, zmin, zmax, geom_origin, confidence,
              topology_status, geom_hash, baunit_id
            ) VALUES (
              :id, :parent_id, :parent_ulpin, :su_class, :local_code, :version, :display_id,
              'ACTIVE', ST_SetSRID(ST_MakeValid(ST_GeomFromText(:wkt)), 32643), :zmin, :zmax,
              'SYNTHETIC', :confidence, :topology_status, :geom_hash, :baunit_id
            )
            """
        ),
        {
            "id": kw["id"],
            "parent_id": kw.get("parent_id"),
            "parent_ulpin": PARENT_ULPIN,
            "su_class": kw["su_class"],
            "local_code": kw["local_code"],
            "version": kw.get("version", 1),
            "display_id": f"UNISSUED/{kw['id']}",
            "wkt": kw["poly"].wkt,
            "zmin": kw["zmin"],
            "zmax": kw["zmax"],
            "confidence": kw.get("confidence", 0.95),
            "topology_status": kw.get("topology_status", "PENDING"),
            "geom_hash": _checksum(kw["poly"].wkt + f"|{kw['zmin']}|{kw['zmax']}"),
            "baunit_id": kw.get("baunit_id"),
        },
    )
    return kw["id"]


def degrade_without_plans(db: Session) -> dict:
    """Height / 3.0 m whole-floor prisms. Plans missing → DEGRADED, no fake VALID."""
    from shapely import wkt as shapely_wkt

    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))

    b_wkt = db.execute(
        text("SELECT ST_AsText(geom_2d) FROM spatial_unit WHERE su_class='BUILDING' AND status='ACTIVE' AND site_id IS NULL LIMIT 1")
    ).scalar()
    if not b_wkt:
        raise ValueError("seed the demo first")
    poly = shapely_wkt.loads(b_wkt)
    ba = db.execute(text("SELECT id FROM baunit LIMIT 1")).scalar()
    db.execute(text("""
        UPDATE spatial_unit SET status = 'EXTINGUISHED', valid_to = now()
        WHERE su_class IN ('UNIT', 'COMMON') AND status = 'ACTIVE' AND site_id IS NULL
    """))
    floors = db.execute(
        text(
            """
            SELECT id, local_code, zmin, zmax
            FROM spatial_unit WHERE su_class='FLOOR' AND status='ACTIVE' AND site_id IS NULL ORDER BY zmin
            """
        )
    ).mappings().all()
    wholes = []
    for fl in floors:
        if float(fl["zmax"]) <= STOREY_M + 0.01:
            continue
        level = int(round(float(fl["zmax"]) / STOREY_M))
        code = f"F{level:02d}-WHOLE"
        version = db.execute(text("""
            SELECT COALESCE(MAX(version), 0) + 1 FROM spatial_unit
            WHERE parent_ulpin = :parent AND su_class = 'UNIT' AND local_code = :code
        """), {"parent": PARENT_ULPIN, "code": code}).scalar_one()
        _insert_su(
            db,
            id=uuid.uuid4(),
            parent_id=fl["id"],
            poly=poly,
            su_class="UNIT",
            local_code=code,
            version=version,
            zmin=float(fl["zmin"]),
            zmax=float(fl["zmax"]),
            topology_status="DEGRADED",
            confidence=0.35,
            baunit_id=ba,
        )
        wholes.append(code)
    extruded = extrude_units(db)
    db.execute(text("""
        UPDATE building SET extraction_method = 'HEIGHT_3M_NO_PLANS'
        WHERE spatial_unit_id IN (SELECT id FROM spatial_unit WHERE site_id IS NULL)
    """))
    return {
        "mode": "DEGRADED_NO_PLANS",
        "whole_floor_units": wholes,
        "extruded_solids": extruded,
        "note": "No floor plans: 3.0 m whole-floor prisms. Confidence dropped. No fake VALID. Proposed 3D ULPIN not issued.",
    }


def _write_demo_files(demo_dir: Path, features: list[dict], util_lines: list[tuple]):
    demo_dir.mkdir(parents=True, exist_ok=True)
    site = {
        "name": SITE_NAME,
        "source_epsg": 4326,
        "storage_epsg": 32643,
        "z_ref": "LOCAL_SITE",
        "parent_ulpin": PARENT_ULPIN,
        "origin_lon": ORIGIN_LON,
        "origin_lat": ORIGIN_LAT,
        "storey_m": STOREY_M,
        "floors": FLOORS,
        "geom_origin": "SYNTHETIC",
        "demo_freeze": "sih26011-kothrud-v01",
        "gnss_cors": {
            "method": "CORS",
            "h_rmse_m": 0.05,
            "v_rmse_m": 0.08,
            "live_stream": False,
            "note": "Operator-declared synthetic accuracy. Not a live CORS client. Not survey certification.",
        },
        "note": "Synthetic georeferenced Kothrud/Pune scene. Not official cadastral or ULPIN data.",
    }
    (demo_dir / "site.json").write_text(json.dumps(site, indent=2), encoding="utf-8")

    def fc(name, feats):
        (demo_dir / name).write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
                    "features": feats,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    by = {}
    for f in features:
        by.setdefault(f["kind"], []).append(
            {
                "type": "Feature",
                "properties": {k: v for k, v in f.items() if k not in ("kind", "poly")},
                "geometry": to_wgs_geojson(f["poly"]),
            }
        )
    fc("parcel.geojson", by.get("PARCEL", []))
    fc("building.geojson", by.get("BUILDING", []))
    fc("units.geojson", by.get("UNIT", []) + by.get("COMMON", []) + by.get("PARKING", []) + by.get("AIR", []) + by.get("TRANSPORT", []))
    fc("floors.geojson", by.get("FLOOR", []))
    util_feats = []
    for line, props in util_lines:
        util_wgs = mapping(shp_transform(lambda x, y, z=None: utm_to_lonlat(x, y), line))
        util_feats.append(
            {
                "type": "Feature",
                "properties": props,
                "geometry": util_wgs,
            }
        )
    fc("utilities.geojson", util_feats)
    fc("overlap_error.geojson", by.get("OVERLAP", []))
    (demo_dir / "bad_no_crs.json").write_text(
        json.dumps({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}),
        encoding="utf-8",
    )


def seed_demo(db: Session) -> dict:
    db.execute(text("SELECT pg_advisory_xact_lock(26011)"))
    if db.execute(text("""
        SELECT EXISTS(SELECT 1 FROM source_dataset WHERE site_id IS NOT NULL OR meta ? 'source_geojson')
            OR EXISTS(SELECT 1 FROM site WHERE meta->>'synthetic' IS DISTINCT FROM 'true')
    """)).scalar():
        raise ImportConflict("Demo reset is disabled while user-created sites or datasets exist; use a separate demo database.")
    db.execute(text("TRUNCATE validation_result, rrr, floor, building, spatial_unit, baunit, party, source_dataset, site CASCADE"))

    ox, oy = lonlat_to_utm(ORIGIN_LON, ORIGIN_LAT)
    px, py, pw, ph = PARCEL
    bx, by, bw, bh = BUILDING
    parcel = rect_from_origin(ox, oy, px, py, pw, ph)
    building = rect_from_origin(ox, oy, bx, by, bw, bh)

    west_w = (bw - CORRIDOR_W) / 2.0
    unit_w = west_w
    unit_e_x = bx + west_w + CORRIDOR_W
    corridor = rect_from_origin(ox, oy, bx + west_w, by, CORRIDOR_W, bh)
    unit_west = rect_from_origin(ox, oy, bx, by, unit_w, bh)
    unit_east = rect_from_origin(ox, oy, unit_e_x, by, unit_w, bh)

    z_ground, z_roof = 0.0, FLOORS * STOREY_M
    ids = {k: uuid.uuid4() for k in ["parcel", "building", "ba", "assoc", "owner", "water", "sewer", "air", "transport"]}

    db.execute(
        text("INSERT INTO party (id, party_type, name) VALUES (:id, 'association', 'Demo Apartment Association')"),
        {"id": ids["assoc"]},
    )
    db.execute(
        text("INSERT INTO party (id, party_type, name) VALUES (:id, 'person', 'Allottee A (synthetic)')"),
        {"id": ids["owner"]},
    )
    db.execute(
        text("INSERT INTO party (id, party_type, name) VALUES (:id, 'organisation', 'Demo municipal water (synthetic)')"),
        {"id": ids["water"]},
    )
    db.execute(
        text("INSERT INTO party (id, party_type, name) VALUES (:id, 'organisation', 'Demo municipal sewer (synthetic)')"),
        {"id": ids["sewer"]},
    )
    db.execute(
        text("INSERT INTO party (id, party_type, name) VALUES (:id, 'organisation', 'Demo municipal transport (synthetic)')"),
        {"id": ids["transport"]},
    )
    db.execute(
        text("INSERT INTO baunit (id, name, uid) VALUES (:id, 'Kothrud demo scheme', 'BA-PUNE-DEMO-01')"),
        {"id": ids["ba"]},
    )
    db.execute(
        text(
            """
            INSERT INTO site (name, storage_epsg, source_epsg, z_ref, parent_ulpin, bbox, meta)
            VALUES (:name, 32643, 4326, 'LOCAL_SITE', :ulpin, ST_SetSRID(ST_GeomFromText(:wkt), 32643), :meta)
            """
        ),
        {
            "name": SITE_NAME,
            "ulpin": PARENT_ULPIN,
            "wkt": parcel.wkt,
            "meta": json.dumps({
                "synthetic": True,
                "city": "Pune",
                "gnss_cors": {
                    "method": "CORS",
                    "h_rmse_m": 0.05,
                    "v_rmse_m": 0.08,
                    "live_stream": False,
                    "note": "Operator-declared synthetic accuracy. Not a live CORS client.",
                },
            }),
        },
    )
    db.execute(
        text(
            """
            INSERT INTO source_dataset (kind, filename, checksum_sha256, epsg, z_ref, meta)
            VALUES ('geojson', 'demo/site.json', :ck, 4326, 'LOCAL_SITE', :meta)
            """
        ),
        {"ck": _checksum(PARENT_ULPIN), "meta": json.dumps({"note": "synthetic demo"})},
    )

    _insert_su(
        db,
        id=ids["parcel"],
        poly=parcel,
        su_class="PARCEL",
        local_code="LOT",
        zmin=-5.0,
        zmax=z_roof + 12.0,
        confidence=0.99,
        baunit_id=ids["ba"],
        topology_status="VALID",
    )
    _insert_su(
        db,
        id=ids["building"],
        parent_id=ids["parcel"],
        poly=building,
        su_class="BUILDING",
        local_code="B1",
        zmin=z_ground,
        zmax=z_roof,
        confidence=0.9,
        topology_status="VALID",
    )
    db.execute(
        text(
            """
            INSERT INTO building (spatial_unit_id, storeys_above, storeys_below, z_ground, z_roof, extraction_method)
            VALUES (:sid, :n, 0, :zg, :zr, 'authored-demo')
            """
        ),
        {"sid": ids["building"], "n": FLOORS, "zg": z_ground, "zr": z_roof},
    )
    bldg_row = db.execute(
        text("SELECT id FROM building WHERE spatial_unit_id = :sid"), {"sid": ids["building"]}
    ).scalar()

    features = [
        {"kind": "PARCEL", "poly": parcel, "local_code": "LOT", "su_class": "PARCEL"},
        {"kind": "BUILDING", "poly": building, "local_code": "B1", "su_class": "BUILDING"},
    ]

    for level in range(1, FLOORS + 1):
        z0, z1 = (level - 1) * STOREY_M, level * STOREY_M
        fl_id = uuid.uuid4()
        fl_code = f"F{level:02d}"
        _insert_su(
            db,
            id=fl_id,
            parent_id=ids["building"],
            poly=building,
            su_class="FLOOR",
            local_code=fl_code,
            zmin=z0,
            zmax=z1,
            topology_status="VALID",
        )
        db.execute(
            text(
                "INSERT INTO floor (building_id, spatial_unit_id, level_index, label) VALUES (:b, :s, :i, :l)"
            ),
            {"b": bldg_row, "s": fl_id, "i": level, "l": "G" if level == 1 else str(level)},
        )
        features.append({"kind": "FLOOR", "poly": building, "local_code": fl_code, "level": level, "zmin": z0, "zmax": z1})

        if level == 1:
            park_id = uuid.uuid4()
            _insert_su(
                db,
                id=park_id,
                parent_id=fl_id,
                poly=building,
                su_class="PARKING",
                local_code="F01-PARK",
                zmin=z0,
                zmax=z1,
                topology_status="VALID",
                baunit_id=ids["ba"],
            )
            features.append({"kind": "PARKING", "poly": building, "local_code": "F01-PARK", "zmin": z0, "zmax": z1})
            continue

        west_id, east_id, com_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        west_code = f"F{level:02d}-U{level}01"
        east_code = f"F{level:02d}-U{level}02"
        com_code = f"F{level:02d}-COMMON"
        _insert_su(db, id=west_id, parent_id=fl_id, poly=unit_west, su_class="UNIT", local_code=west_code, zmin=z0, zmax=z1, topology_status="VALID", baunit_id=ids["ba"])
        _insert_su(db, id=east_id, parent_id=fl_id, poly=unit_east, su_class="UNIT", local_code=east_code, zmin=z0, zmax=z1, topology_status="VALID", baunit_id=ids["ba"])
        _insert_su(db, id=com_id, parent_id=fl_id, poly=corridor, su_class="COMMON", local_code=com_code, zmin=z0, zmax=z1, topology_status="VALID", baunit_id=ids["ba"])
        db.execute(
            text(
                """
                INSERT INTO rrr (baunit_id, party_id, spatial_unit_id, rrr_type, share, description)
                VALUES (:ba, :p, :su, 'RIGHT', 0.5, 'undivided share in common corridor (RERA-style, synthetic)')
                """
            ),
            {"ba": ids["ba"], "p": ids["assoc"], "su": com_id},
        )
        features.extend(
            [
                {"kind": "UNIT", "poly": unit_west, "local_code": west_code, "zmin": z0, "zmax": z1},
                {"kind": "UNIT", "poly": unit_east, "local_code": east_code, "zmin": z0, "zmax": z1},
                {"kind": "COMMON", "poly": corridor, "local_code": com_code, "zmin": z0, "zmax": z1},
            ]
        )

    overlap_id = uuid.uuid4()
    _insert_su(
        db,
        id=overlap_id,
        parent_id=ids["building"],
        poly=unit_west,
        su_class="UNIT",
        local_code="F05-U501-DUP",
        zmin=4 * STOREY_M,
        zmax=5 * STOREY_M,
        topology_status="INVALID",
        confidence=0.2,
    )
    features.append(
        {
            "kind": "OVERLAP",
            "poly": unit_west,
            "local_code": "F05-U501-DUP",
            "zmin": 4 * STOREY_M,
            "zmax": 5 * STOREY_M,
            "note": "seeded topology error",
        }
    )

    util = LineString(
        [
            (ox + 4.0, oy + 3.0),
            (ox + 38.0, oy + 3.0),
        ]
    )
    # corridor prism as a thin rectangle along the south setback
    util_poly = rect_from_origin(ox, oy, 4.0, 2.7, 34.0, 0.6)
    util_id = uuid.uuid4()
    _insert_su(
        db,
        id=util_id,
        parent_id=ids["parcel"],
        poly=util_poly,
        su_class="UTILITY",
        local_code="UTL-WTR-01",
        zmin=-3.2,
        zmax=-2.6,
        topology_status="VALID",
        confidence=0.6,
    )
    db.execute(
        text(
            """
            INSERT INTO rrr (baunit_id, party_id, spatial_unit_id, rrr_type, share, description)
            VALUES (
              :ba, :p, :su, 'RESTRICTION', NULL,
              'easement-style restriction for underground water main. Not a new statute. Depth assumed.'
            )
            """
        ),
        {"ba": ids["ba"], "p": ids["water"], "su": util_id},
    )

    sewer = LineString(
        [
            (ox + 4.0, oy + 28.8),
            (ox + 38.0, oy + 28.8),
        ]
    )
    sewer_poly = rect_from_origin(ox, oy, 4.0, 28.5, 34.0, 0.6)
    sewer_id = uuid.uuid4()
    _insert_su(
        db,
        id=sewer_id,
        parent_id=ids["parcel"],
        poly=sewer_poly,
        su_class="UTILITY",
        local_code="UTL-SWR-01",
        zmin=-4.4,
        zmax=-3.8,
        topology_status="VALID",
        confidence=0.55,
    )
    db.execute(
        text(
            """
            INSERT INTO rrr (baunit_id, party_id, spatial_unit_id, rrr_type, share, description)
            VALUES (
              :ba, :p, :su, 'RESTRICTION', NULL,
              'easement-style restriction for underground sewer. Not a new statute. Depth assumed.'
            )
            """
        ),
        {"ba": ids["ba"], "p": ids["sewer"], "su": sewer_id},
    )

    _insert_su(
        db,
        id=ids["air"],
        parent_id=ids["parcel"],
        poly=building,
        su_class="AIR",
        local_code="AIR-B1",
        zmin=z_roof,
        zmax=z_roof + 10.0,
        topology_status="VALID",
        confidence=0.7,
        baunit_id=ids["ba"],
    )
    features.append(
        {
            "kind": "AIR",
            "poly": building,
            "local_code": "AIR-B1",
            "zmin": z_roof,
            "zmax": z_roof + 10.0,
            "note": "air-rights slab above authored roof. Proposed volume, not a title.",
        }
    )

    # West setback flyover: beside the building, not through it. Elevated LOCAL_SITE metres.
    transport_poly = rect_from_origin(ox, oy, 1.5, 0.5, 6.0, 31.0)
    trn_id = uuid.uuid4()
    _insert_su(
        db,
        id=trn_id,
        parent_id=ids["parcel"],
        poly=transport_poly,
        su_class="TRANSPORT",
        local_code="TRN-ELV-01",
        zmin=8.0,
        zmax=14.0,
        topology_status="VALID",
        confidence=0.6,
        baunit_id=ids["ba"],
    )
    db.execute(
        text(
            """
            INSERT INTO rrr (baunit_id, party_id, spatial_unit_id, rrr_type, share, description)
            VALUES (
              :ba, :p, :su, 'RESTRICTION', NULL,
              'easement-style restriction for an elevated transport corridor. Proposed volume, not a new statute.'
            )
            """
        ),
        {"ba": ids["ba"], "p": ids["transport"], "su": trn_id},
    )
    features.append(
        {
            "kind": "TRANSPORT",
            "poly": transport_poly,
            "local_code": "TRN-ELV-01",
            "zmin": 8.0,
            "zmax": 14.0,
            "note": "elevated flyover in the west setback. Proposed volume, not a title.",
        }
    )
    util_lines = [
        (
            util,
            {
                "local_code": "UTL-WTR-01",
                "su_class": "UTILITY",
                "diameter_m": 0.3,
                "zmin": -3.2,
                "zmax": -2.6,
                "assumed_depth": True,
            },
        ),
        (
            sewer,
            {
                "local_code": "UTL-SWR-01",
                "su_class": "UTILITY",
                "diameter_m": 0.3,
                "zmin": -4.4,
                "zmax": -3.8,
                "assumed_depth": True,
            },
        ),
    ]

    from app.validate import run_validation

    extruded = extrude_units(db)
    validation = run_validation(db)
    valid_units = db.execute(text("""
        SELECT id, su_class, local_code, version FROM spatial_unit
        WHERE status = 'ACTIVE' AND topology_status = 'VALID'
    """)).mappings().all()
    for unit in valid_units:
        display = issue_display_id(PARENT_ULPIN, unit["su_class"], unit["local_code"], unit["version"])
        db.execute(text("UPDATE spatial_unit SET display_id = :display WHERE id = :id"),
                   {"display": display, "id": unit["id"]})

    demo_dir = Path(settings.demo_dir)
    _write_demo_files(demo_dir, features, util_lines)

    n = db.execute(text("SELECT count(*) FROM spatial_unit")).scalar()
    return {
        "parent_ulpin": PARENT_ULPIN,
        "parent_ulpin_note": "placeholder 14-char parent; not a government-issued ULPIN",
        "spatial_units": n,
        "extruded_solids": extruded,
        "overlap_hits": [f["detail"] for f in validation["findings"] if f["rule_code"] == "UNIT_OVERLAP"],
        "duplicate_vol": [f["detail"] for f in validation["findings"] if f["rule_code"] == "DUPLICATE_VOL" and not f["passed"]],
        "flat_501": db.execute(text(
            "SELECT display_id FROM spatial_unit WHERE local_code = 'F05-U501'"
        )).scalar_one(),
        "air_rights": db.execute(text(
            "SELECT display_id FROM spatial_unit WHERE local_code = 'AIR-B1'"
        )).scalar_one(),
        "elevated_transport": db.execute(text(
            "SELECT display_id FROM spatial_unit WHERE local_code = 'TRN-ELV-01'"
        )).scalar_one(),
        "demo_dir": str(demo_dir),
    }
