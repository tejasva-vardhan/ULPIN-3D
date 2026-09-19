from sqlalchemy import text
from sqlalchemy.orm import Session


def extrude_units(db: Session, unit_ids=None) -> int:
    """Build solids only for selected active prism records (all active if omitted)."""
    enabled = db.execute(text(
        "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='postgis_sfcgal')"
    )).scalar()
    if not enabled:
        raise RuntimeError("postgis_sfcgal is required to construct solids.")
    rows = db.execute(text("""
        UPDATE spatial_unit
        SET geom_3d = ST_SetSRID(
              ST_Translate(CG_Extrude(ST_Force2D(geom_2d), 0, 0, zmax - zmin), 0, 0, zmin), 32643),
            -- Translate near the origin for stable volume arithmetic at UTM magnitudes.
            volume_m3 = CG_Volume(CG_MakeSolid(CG_Extrude(
                ST_Translate(ST_Force2D(geom_2d),
                    -ST_XMin(Box3D(geom_2d)), -ST_YMin(Box3D(geom_2d)), 0),
                0, 0, zmax - zmin)))
        WHERE status = 'ACTIVE' AND (:all_units OR id = ANY(CAST(:ids AS uuid[])))
        RETURNING id
    """), {"all_units": unit_ids is None, "ids": list(unit_ids or [])}).all()
    return len(rows)
