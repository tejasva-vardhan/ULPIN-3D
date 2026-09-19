"""Reported GNSS/CORS control-point provenance; no survey certification."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.geo import CrsError
from app.ingest import ImportConflict, get_dataset


class SurveyDeclaration(BaseModel):
    model_config = ConfigDict(extra='forbid')

    method: Literal['GNSS', 'CORS', 'TOTAL_STATION', 'PHOTOGRAMMETRY']
    h_rmse_m: float = Field(gt=0, le=100, allow_inf_nan=False)
    v_rmse_m: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)
    evidence_ref: str = Field(min_length=1, max_length=500)


def _source(db, dataset_id: UUID):
    source = get_dataset(db, dataset_id)
    if not source or not source['site_id'] or source['kind'] != 'survey-control':
        raise CrsError('Use a site-scoped survey-control GeoJSON dataset')
    features = source['meta'].get('features', [])
    if not features or any(f['geometry']['type'] != 'Point' or
                           len(f['geometry']['coordinates']) != 2 for f in features):
        raise CrsError('Survey-control source must contain 2D Point features only')
    return source, len(features)


def get_survey(db, dataset_id: UUID):
    source, point_count = _source(db, dataset_id)
    row = db.execute(text('''
        SELECT id::text AS id, method, h_rmse_m, v_rmse_m, evidence_ref
        FROM survey WHERE source_id=:source
    '''), {'source': dataset_id}).mappings().first()
    if not row:
        return None
    return {**dict(row), 'h_rmse_m': float(row['h_rmse_m']),
            'v_rmse_m': float(row['v_rmse_m']) if row['v_rmse_m'] is not None else None,
            'source_dataset_id': source['id'], 'site_id': source['site_id'],
            'source_epsg': source['epsg'], 'point_count': point_count,
            'source_checksum_sha256': source['checksum_sha256'],
            'accuracy_kind': 'operator-reported; not independently verified'}


def record_survey(db, dataset_id: UUID, declaration: SurveyDeclaration):
    _source(db, dataset_id)
    db.execute(text('SELECT pg_advisory_xact_lock(26011)'))
    existing = get_survey(db, dataset_id)
    if existing:
        same = (existing['method'] == declaration.method and
                existing['h_rmse_m'] == declaration.h_rmse_m and
                existing['v_rmse_m'] == declaration.v_rmse_m and
                existing['evidence_ref'] == declaration.evidence_ref.strip())
        if not same:
            raise ImportConflict('Survey declaration already exists for this source; create a new source for revised evidence')
        return {**existing, 'reused': True}
    evidence_ref = declaration.evidence_ref.strip()
    if not evidence_ref:
        raise CrsError('evidence_ref must identify the survey report or source')
    db.execute(text('''
        INSERT INTO survey (method, h_rmse_m, v_rmse_m, source_id, evidence_ref)
        VALUES (:method, :horizontal, :vertical, :source, :evidence)
    '''), {'method': declaration.method, 'horizontal': declaration.h_rmse_m,
           'vertical': declaration.v_rmse_m, 'source': dataset_id,
           'evidence': evidence_ref})
    return {**get_survey(db, dataset_id), 'reused': False}
