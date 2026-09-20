from math import isclose

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def check_database(conn) -> dict:
    """Require the schema and exercise the solid functions used by the demo."""
    ready = conn.execute(text("""
        SELECT to_regclass('spatial_unit') IS NOT NULL AS schema_ready,
               EXISTS(SELECT 1 FROM pg_extension WHERE extname='postgis_sfcgal') AS sfcgal
    """)).mappings().one()
    if not ready["schema_ready"]:
        raise RuntimeError("Database schema is missing; initialize it with backend/sql/init.sql.")
    if not ready["sfcgal"]:
        raise RuntimeError("postgis_sfcgal is required for 3D solids; enable it in the database.")
    volume = conn.execute(text("""
        SELECT CG_Volume(CG_MakeSolid(CG_Extrude(
            ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))', 32643),
            0, 0, 1)))
    """)).scalar_one()
    if volume is None or not isclose(float(volume), 1.0, rel_tol=0, abs_tol=1e-6):
        raise RuntimeError("SFCGAL solid check failed: expected a 1 m³ cube.")
    return {
        "postgis": conn.execute(text("SELECT PostGIS_Version()")).scalar_one(),
        "sfcgal": True,
    }


def ensure_schema() -> None:
    with engine.begin() as conn:
        check_database(conn)
        conn.execute(
            text(
                """
                ALTER TABLE spatial_unit
                  ADD COLUMN IF NOT EXISTS derived_from uuid REFERENCES spatial_unit(id)
                """
            )
        )
        conn.execute(text("ALTER TABLE source_dataset ADD COLUMN IF NOT EXISTS site_id uuid REFERENCES site(id)"))
        conn.execute(text("ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS site_id uuid REFERENCES site(id)"))
        conn.execute(text("ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS source_dataset_id uuid REFERENCES source_dataset(id)"))
        conn.execute(text("ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS source_feature_index int"))
        conn.execute(text("ALTER TABLE survey ADD COLUMN IF NOT EXISTS evidence_ref text"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS survey_source_unique ON survey (source_id) WHERE source_id IS NOT NULL"))

        # Task 5: rights recording (evidence + claim vs. verified title) and
        # explicit geometry review, plus lifecycle reason/actor on withdrawal.
        conn.execute(text("ALTER TABLE rrr ADD COLUMN IF NOT EXISTS evidence_ref text"))
        conn.execute(text("ALTER TABLE rrr ADD COLUMN IF NOT EXISTS claim_status text NOT NULL DEFAULT 'CLAIMED'"))
        conn.execute(text("ALTER TABLE rrr ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now()"))
        conn.execute(text(
            """
            DO $$ BEGIN
              ALTER TABLE rrr ADD CONSTRAINT rrr_claim_status_chk CHECK (claim_status IN ('CLAIMED','VERIFIED'));
            EXCEPTION WHEN duplicate_object THEN NULL; END $$
            """
        ))
        conn.execute(text(
            """
            DO $$ BEGIN
              ALTER TABLE rrr ADD CONSTRAINT rrr_right_share_range_chk
                CHECK (rrr_type <> 'RIGHT' OR share IS NULL OR (share > 0 AND share <= 1));
            EXCEPTION WHEN duplicate_object THEN NULL; END $$
            """
        ))

        conn.execute(text("ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS status_reason text"))
        conn.execute(text("ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS status_actor text"))

        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS spatial_unit_review (
              id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
              spatial_unit_id  uuid NOT NULL REFERENCES spatial_unit(id),
              decision         text NOT NULL,
              reviewer_label   text NOT NULL,
              reason           text,
              evidence_ref     text,
              released_block   boolean NOT NULL DEFAULT false,
              created_at       timestamptz NOT NULL DEFAULT now()
            )
            """
        ))
        conn.execute(text(
            """
            DO $$ BEGIN
              ALTER TABLE spatial_unit_review ADD CONSTRAINT su_review_decision_chk
                CHECK (decision IN ('APPROVED','REJECTED'));
            EXCEPTION WHEN duplicate_object THEN NULL; END $$
            """
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS su_review_unit_idx ON spatial_unit_review (spatial_unit_id)"
        ))

        conn.execute(text("""
ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS review_required boolean NOT NULL DEFAULT false;
UPDATE spatial_unit SET review_required=true WHERE NOT review_required AND
    (topology_status='DEGRADED' OR EXISTS
      (SELECT 1 FROM spatial_unit_review r WHERE r.spatial_unit_id=spatial_unit.id));
        """))
        conn.execute(text("ALTER TYPE su_class ADD VALUE IF NOT EXISTS 'TRANSPORT'"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
