"""Connect uploaded elevation evidence to persisted, review-required proposals."""

import json
from pathlib import Path
from uuid import UUID

import numpy as np
from pydantic import BaseModel, Field, model_validator
from shapely import wkt
from shapely.geometry import mapping, shape
from sqlalchemy import text

from app.config import settings
from app.geo import CrsError
from app.ingest import get_dataset, ingest_dataset
from app.pipeline.assets import asset_path
from app.pipeline.measure import measure_cloud, measure_rasters
from app.properties import CODE, process_dataset


class BuildingRequest(BaseModel):
    site_id: UUID
    parcel_code: str
    building_code: str
    point_cloud_id: UUID | None = None
    dsm_id: UUID | None = None
    dtm_id: UUID | None = None
    plan_dataset_id: UUID | None = None
    cell_m: float = Field(default=0.5, ge=0.1, le=10, allow_inf_nan=False)
    threshold_m: float = Field(default=2.5, gt=0, le=100, allow_inf_nan=False)
    storeys: int | None = Field(default=None, ge=1, le=200)
    assumed_storey_height_m: float = Field(default=3.0, ge=2, le=10, allow_inf_nan=False)

    @model_validator(mode='after')
    def check_sources(self):
        cloud = self.point_cloud_id is not None
        pair = self.dsm_id is not None and self.dtm_id is not None
        if not ((cloud and self.dsm_id is None and self.dtm_id is None) or (not cloud and pair)):
            raise ValueError('Supply point_cloud_id OR both dsm_id and dtm_id')
        if not CODE.fullmatch(self.building_code) or len(self.building_code) > 65:
            raise ValueError('building_code must be a short identifier (up to 65 characters)')
        return self


def process_building_sources(db, request: BuildingRequest):
    db.execute(text('SELECT pg_advisory_xact_lock(26011)'))
    parcel_row = db.execute(text("""
        SELECT ST_AsText(geom_2d) AS wkt FROM spatial_unit
        WHERE site_id=:site AND local_code=:code AND su_class='PARCEL' AND status='ACTIVE'
    """), {'site': request.site_id, 'code': request.parcel_code}).mappings().first()
    if not parcel_row:
        raise CrsError('Import and process the parent parcel in this site first')
    parcel = wkt.loads(parcel_row['wkt'])

    def source(dataset_id, kind=None):
        row = get_dataset(db, dataset_id)
        if not row or row['site_id'] != str(request.site_id) or (kind and row['kind'] != kind):
            raise CrsError(f'Dataset {dataset_id} must belong to this site' + (f' and have kind {kind}' if kind else ''))
        return row

    plan = source(request.plan_dataset_id) if request.plan_dataset_id else None
    footprint = None
    if plan:
        matches = [f for f in plan['meta'].get('features', [])
                   if f['properties'].get('local_code') == request.building_code
                   and f['properties'].get('su_class') == 'BUILDING']
        if len(matches) != 1:
            raise CrsError('Plan dataset must contain exactly one matching BUILDING feature')
        footprint = shape(matches[0]['geometry'])
        if footprint.geom_type != 'Polygon' or not parcel.buffer(0.03).covers(footprint):
            raise CrsError('Plan building footprint must be a polygon within the selected parcel')
    if request.point_cloud_id:
        inputs = [source(request.point_cloud_id, 'las')]
        cloud = inputs[0]
        measured = measure_cloud(asset_path(cloud, settings.upload_dir), cloud['epsg'],
            cloud['meta']['local_zero_m'], parcel, cell_m=request.cell_m,
            threshold_m=request.threshold_m, footprint=footprint)
    else:
        inputs = [source(request.dsm_id, 'dsm'), source(request.dtm_id, 'dtm')]
        measured = measure_rasters(asset_path(inputs[0], settings.upload_dir),
            asset_path(inputs[1], settings.upload_dir), inputs[0]['meta'], inputs[1]['meta'],
            parcel, threshold_m=request.threshold_m, footprint=footprint)
    metrics = {k: v for k, v in measured.items() if k != 'footprint'}
    metrics['footprint_wkt'] = measured['footprint'].wkt
    metrics['site_id'] = str(request.site_id)
    metrics['parameters'] = request.model_dump(mode='json')
    metrics['inputs'] = [{'id': row['id'], 'checksum_sha256': row['checksum_sha256'],
                         'filename': row['filename'], 'z_ref': row['z_ref'],
                         'local_zero_m': row['meta']['local_zero_m']} for row in inputs]
    if plan:
        result = process_dataset(db, UUID(plan['id']))
        metrics['plans_preserved'] = True
        metrics['plan_source'] = {'id': plan['id'], 'checksum_sha256': plan['checksum_sha256']}
        plan_props = matches[0]['properties']
        metrics['plan_height_m'] = float(plan_props['zmax']) - float(plan_props['zmin'])
        metrics['height_difference_from_plan_m'] = measured['height_m'] - metrics['plan_height_m']
        metrics['assumptions'].append('Plan boundaries and levels take precedence; measured heights did not overwrite them')
        inputs.append(plan)
    else:
        floors = request.storeys or max(1, int(np.floor(measured['height_m'] / request.assumed_storey_height_m + 0.5)))
        if floors > 200:
            raise CrsError('Estimated floor count exceeds the prototype limit')
        metrics['floor_count'] = floors
        metrics['assumptions'].append('Equal-height floors are proposals; no internal slabs or apartment boundaries were observed')
        if request.storeys is None:
            metrics['assumptions'].append(f'Floor count inferred using assumed {request.assumed_storey_height_m} m storeys')
        origin = 'SYNTHETIC' if any(row['meta']['geom_origin'] == 'SYNTHETIC' for row in inputs) else 'AI_DERIVED'
        def feature(code, cls, parent, zmin, zmax, **extra):
            return {'type':'Feature', 'id':code, 'geometry':mapping(measured['footprint']),
                    'properties': {'local_code':code,'su_class':cls,'parent_code':parent,
                        'zmin':float(zmin),'zmax':float(zmax),'geom_origin':origin,
                        'confidence':measured['confidence'],'requires_review':True, **extra}}
        features = [feature(request.building_code, 'BUILDING', request.parcel_code,
                            measured['ground_z'], measured['roof_z'])]
        levels = np.linspace(measured['ground_z'], measured['roof_z'], floors + 1)
        for i in range(floors):
            features.append(feature(f'{request.building_code}-F{i+1:02d}', 'FLOOR', request.building_code,
                                    levels[i], levels[i+1], level_index=i+1, label=f'Proposed floor {i+1}'))
        generated = ingest_dataset(db, {'site_id':str(request.site_id), 'epsg':32643,
            'kind':'derived-building', 'filename':f'{request.building_code}-proposal.geojson',
            'geom_origin':origin, 'geojson':{'type':'FeatureCollection','features':features,
                                          'processing':metrics}}, Path(settings.demo_dir))
        result = process_dataset(db, UUID(generated['id']))
        db.execute(text("UPDATE source_dataset SET meta=meta || CAST(:meta AS jsonb) WHERE id=:id"),
                   {'id':generated['id'],'meta':json.dumps({'processing':metrics})})
    run_id = db.execute(text("""
        INSERT INTO process_run (stage, processor_ver, source_ids, metrics, finished_at)
        VALUES ('building_from_sources', :version, :sources, CAST(:metrics AS jsonb), clock_timestamp())
        RETURNING id
    """), {'version':settings.processor_ver, 'sources':[UUID(row['id']) for row in inputs],
           'metrics':json.dumps({**metrics,'output_dataset_id':result['dataset_id']})}).scalar_one()
    return {**result, 'run_id':str(run_id), 'metrics':metrics,
            'note':'Plans are preserved when supplied. Otherwise building/floors require review and cannot be issued.'}
