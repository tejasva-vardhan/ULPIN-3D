CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE EXTENSION IF NOT EXISTS postgis_sfcgal;

DO $$ BEGIN
  CREATE TYPE su_class AS ENUM (
    'PARCEL','BUILDING','FLOOR','UNIT','COMMON','PARKING',
    'BALCONY','AIR','SUBSURFACE','UTILITY','TRANSPORT'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE geom_origin AS ENUM (
    'SURVEY','PLAN','AI_DERIVED','SYNTHETIC','MANUAL'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE topology_status AS ENUM (
    'PENDING','VALID','INVALID','DEGRADED'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE rrr_type AS ENUM (
    'RIGHT','RESTRICTION','RESPONSIBILITY'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE object_status AS ENUM (
    'ACTIVE','SUPERSEDED','EXTINGUISHED'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS source_dataset (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind            text NOT NULL,
  filename        text NOT NULL,
  checksum_sha256 text NOT NULL,
  epsg            int,
  z_ref           text,
  acquired_at     timestamptz,
  ingested_at     timestamptz NOT NULL DEFAULT now(),
  meta            jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS survey (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  method    text,
  h_rmse_m  numeric,
  v_rmse_m  numeric,
  source_id uuid REFERENCES source_dataset(id)
);

ALTER TABLE survey ADD COLUMN IF NOT EXISTS evidence_ref text;
CREATE UNIQUE INDEX IF NOT EXISTS survey_source_unique ON survey (source_id)
  WHERE source_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS party (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_type text NOT NULL,
  name       text NOT NULL,
  ext_ref    text
);

CREATE TABLE IF NOT EXISTS baunit (
  id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text,
  uid  text UNIQUE
);

CREATE TABLE IF NOT EXISTS spatial_unit (
  id              uuid PRIMARY KEY,
  parent_id       uuid REFERENCES spatial_unit(id),
  parent_ulpin    text,
  su_class        su_class NOT NULL,
  local_code      text NOT NULL,
  version         int NOT NULL DEFAULT 1,
  display_id      text NOT NULL UNIQUE,
  status          object_status NOT NULL DEFAULT 'ACTIVE',
  geom_2d         geometry(Polygon, 32643) NOT NULL,
  zmin            double precision NOT NULL,
  zmax            double precision NOT NULL,
  geom_3d         geometry(PolyhedralSurfaceZ, 32643),
  volume_m3       double precision,
  geom_origin     geom_origin NOT NULL,
  confidence      numeric CHECK (confidence BETWEEN 0 AND 1),
  topology_status topology_status NOT NULL DEFAULT 'PENDING',
  geom_hash       text,
  baunit_id       uuid REFERENCES baunit(id),
  derived_from    uuid REFERENCES spatial_unit(id),
  valid_from      timestamptz NOT NULL DEFAULT now(),
  valid_to        timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (zmax > zmin),
  UNIQUE (parent_ulpin, su_class, local_code, version)
);

CREATE INDEX IF NOT EXISTS su_gix_2d ON spatial_unit USING GIST (geom_2d);
CREATE INDEX IF NOT EXISTS su_parent ON spatial_unit (parent_id);
CREATE INDEX IF NOT EXISTS su_class_idx ON spatial_unit (su_class);

CREATE TABLE IF NOT EXISTS building (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  spatial_unit_id   uuid UNIQUE REFERENCES spatial_unit(id),
  storeys_above     int,
  storeys_below     int,
  z_ground          double precision,
  z_roof            double precision,
  extraction_method text
);

CREATE TABLE IF NOT EXISTS floor (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id     uuid REFERENCES building(id),
  spatial_unit_id uuid UNIQUE REFERENCES spatial_unit(id),
  level_index     int NOT NULL,
  label           text
);

CREATE TABLE IF NOT EXISTS rrr (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  baunit_id       uuid NOT NULL REFERENCES baunit(id),
  party_id        uuid NOT NULL REFERENCES party(id),
  spatial_unit_id uuid REFERENCES spatial_unit(id),
  rrr_type        rrr_type NOT NULL,
  share           numeric,
  description     text,
  UNIQUE (baunit_id, party_id, spatial_unit_id, rrr_type)
);

CREATE TABLE IF NOT EXISTS validation_result (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  spatial_unit_id uuid REFERENCES spatial_unit(id),
  run_id          uuid NOT NULL,
  rule_code       text NOT NULL,
  passed          boolean NOT NULL,
  severity        text NOT NULL,
  detail          jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS process_run (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stage         text NOT NULL,
  processor_ver text NOT NULL,
  source_ids    uuid[],
  metrics       jsonb,
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz
);

CREATE TABLE IF NOT EXISTS site (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  storage_epsg int NOT NULL DEFAULT 32643,
  source_epsg  int NOT NULL,
  z_ref      text NOT NULL,
  parent_ulpin text NOT NULL,
  bbox       geometry(Polygon, 32643),
  meta       jsonb NOT NULL DEFAULT '{}'
);

-- Additive upgrades for existing databases as well as fresh installations.
ALTER TABLE source_dataset ADD COLUMN IF NOT EXISTS site_id uuid REFERENCES site(id);
ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS site_id uuid REFERENCES site(id);
ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS source_dataset_id uuid REFERENCES source_dataset(id);
ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS source_feature_index int;

-- Task 5: rights recording (evidence + claim vs. verified title) and
-- explicit geometry review, plus lifecycle reason/actor on withdrawal.
ALTER TABLE rrr ADD COLUMN IF NOT EXISTS evidence_ref text;
ALTER TABLE rrr ADD COLUMN IF NOT EXISTS claim_status text NOT NULL DEFAULT 'CLAIMED';
ALTER TABLE rrr ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

DO $$ BEGIN
  ALTER TABLE rrr ADD CONSTRAINT rrr_claim_status_chk CHECK (claim_status IN ('CLAIMED','VERIFIED'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE rrr ADD CONSTRAINT rrr_right_share_range_chk
    CHECK (rrr_type <> 'RIGHT' OR share IS NULL OR (share > 0 AND share <= 1));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS status_reason text;
ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS status_actor text;

CREATE TABLE IF NOT EXISTS spatial_unit_review (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  spatial_unit_id  uuid NOT NULL REFERENCES spatial_unit(id),
  decision         text NOT NULL,
  reviewer_label   text NOT NULL,
  reason           text,
  evidence_ref     text,
  released_block   boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now()
);

DO $$ BEGIN
  ALTER TABLE spatial_unit_review ADD CONSTRAINT su_review_decision_chk
    CHECK (decision IN ('APPROVED','REJECTED'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS su_review_unit_idx ON spatial_unit_review (spatial_unit_id);

ALTER TABLE spatial_unit ADD COLUMN IF NOT EXISTS review_required boolean NOT NULL DEFAULT false;
UPDATE spatial_unit SET review_required=true WHERE NOT review_required AND
    (topology_status='DEGRADED' OR EXISTS
      (SELECT 1 FROM spatial_unit_review r WHERE r.spatial_unit_id=spatial_unit.id));
