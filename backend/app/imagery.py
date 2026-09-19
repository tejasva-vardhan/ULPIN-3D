"""Bounded drone orthophoto evidence, linked to a site but not interpreted as title."""

import json
import math
from pathlib import Path

import rasterio
from pyproj import CRS
from rasterio.warp import transform_bounds
from sqlalchemy import text

from app.geo import CrsError, require_epsg
from app.ingest import get_dataset
from app.pipeline.assets import MAX_CELLS, asset_path, checksum_file


def inspect_orthophoto(path, epsg=None):
    try:
        with rasterio.open(path) as raster:
            if raster.driver != 'GTiff' or raster.count not in (3, 4):
                raise CrsError('Drone orthophoto must be a three- or four-band GeoTIFF')
            if not 0 < raster.width * raster.height <= MAX_CELLS:
                raise CrsError(f'Orthophoto must have 1–{MAX_CELLS} pixels; crop to the site')
            if raster.transform.is_identity or any(t != 'uint8' and t != 'uint16' for t in raster.dtypes):
                raise CrsError('Orthophoto needs an affine georeference and 8- or 16-bit colour bands')
            file_crs = CRS(raster.crs) if raster.crs else None
            header_epsg = file_crs.to_epsg() if file_crs else None
            code = require_epsg(epsg if epsg is not None else header_epsg)
            if file_crs and not file_crs.equals(CRS.from_epsg(code), ignore_axis_order=True):
                raise CrsError('Supplied EPSG conflicts with the orthophoto CRS')
            if not CRS.from_epsg(code).is_projected and code != 4326:
                raise CrsError('Orthophoto CRS must be projected or EPSG:4326')
            bounds = (raster.bounds.left, raster.bounds.bottom,
                      raster.bounds.right, raster.bounds.top)
            storage_bounds = transform_bounds(code, 32643, *bounds, densify_pts=21)
            wgs_bounds = transform_bounds(code, 4326, *bounds, densify_pts=21)
            if not all(math.isfinite(x) for x in (*storage_bounds, *wgs_bounds)):
                raise CrsError('Orthophoto has invalid georeferenced bounds')
            if not 72 <= (wgs_bounds[0] + wgs_bounds[2]) / 2 < 78:
                raise CrsError('Orthophoto is outside the EPSG:32643 longitude zone (72–78°E)')
            return {'source_epsg': code, 'crs_declared_by_uploader': file_crs is None,
                    'width': raster.width, 'height': raster.height, 'bands': raster.count,
                    'dtype': raster.dtypes[0], 'bounds_32643': storage_bounds,
                    'bounds_wgs84': wgs_bounds}
    except CrsError:
        raise
    except Exception as exc:
        raise CrsError(f'Unable to read drone orthophoto: {exc}') from exc


def register_orthophoto(db, path, *, site_id, filename, epsg=None):
    if Path(filename).suffix.lower() not in {'.tif', '.tiff'}:
        raise CrsError('Drone orthophoto filename must end in .tif or .tiff')
    info = inspect_orthophoto(path, epsg)
    site = db.execute(text('SELECT bbox IS NOT NULL AS has_boundary FROM site WHERE id=:id'),
                      {'id': site_id}).mappings().first()
    if not site:
        raise CrsError('Select an existing site')
    if site['has_boundary']:
        bounds = info['bounds_32643']
        overlaps = db.execute(text('''
            SELECT ST_Intersects(bbox, ST_MakeEnvelope(:xmin,:ymin,:xmax,:ymax,32643))
            FROM site WHERE id=:site
        '''), {'xmin': bounds[0], 'ymin': bounds[1], 'xmax': bounds[2],
               'ymax': bounds[3], 'site': site_id}).scalar_one()
        if not overlaps:
            raise CrsError('Orthophoto does not intersect the selected site boundary')
    checksum = checksum_file(path)
    db.execute(text('SELECT pg_advisory_xact_lock(26011)'))
    existing = db.execute(text('''
        SELECT id FROM source_dataset WHERE site_id=:site AND kind='drone-orthophoto'
          AND checksum_sha256=:checksum AND epsg=:epsg
    '''), {'site': site_id, 'checksum': checksum, 'epsg': info['source_epsg']}).scalar()
    if existing:
        return {**get_dataset(db, existing), 'reused': True}
    meta = {**info, 'asset_name': Path(path).name,
            'site_boundary_checked': site['has_boundary'],
            'capture_method': 'drone (operator-declared)',
            'note': 'Image evidence only; no cadastral boundary or building geometry inferred'}
    dataset_id = db.execute(text('''
        INSERT INTO source_dataset (site_id, kind, filename, checksum_sha256, epsg, meta)
        VALUES (:site,'drone-orthophoto',:filename,:checksum,:epsg,CAST(:meta AS jsonb))
        RETURNING id
    '''), {'site': site_id, 'filename': Path(filename).name, 'checksum': checksum,
           'epsg': info['source_epsg'], 'meta': json.dumps(meta)}).scalar_one()
    return {**get_dataset(db, dataset_id), 'reused': False}


def orthophoto_path(db, dataset_id, upload_dir):
    source = get_dataset(db, dataset_id)
    if not source or source['kind'] != 'drone-orthophoto':
        raise CrsError('Drone orthophoto dataset not found')
    return asset_path(source, upload_dir), source
