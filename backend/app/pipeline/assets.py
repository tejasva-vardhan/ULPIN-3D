"""Bounded external elevation assets with explicit horizontal and vertical references."""

import hashlib
import json
import math
from pathlib import Path

import laspy
import rasterio
from pyproj import CRS
from sqlalchemy import text

from app.geo import CrsError, require_epsg
from app.ingest import ORIGINS, get_dataset

MAX_POINTS = 2_000_000
MAX_CELLS = 4_000_000
KINDS = {"las": {".las", ".laz"}, "dsm": {".tif", ".tiff"}, "dtm": {".tif", ".tiff"}}
Z_REFS = {"LOCAL_SITE", "ORTHOMETRIC_EGM", "ELLIPSOIDAL_WGS84"}


def checksum_file(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def inspect_asset(path, kind, epsg=None):
    try:
        if kind == 'las':
            with laspy.open(path) as source:
                if not 0 < source.header.point_count <= MAX_POINTS:
                    raise CrsError(f'Point cloud must contain 1–{MAX_POINTS} points; crop large files first')
                crs = source.header.parse_crs()
                detail = {'point_count': int(source.header.point_count)}
        else:
            with rasterio.open(path) as source:
                if source.driver != 'GTiff' or source.count != 1:
                    raise CrsError('Elevation rasters must be single-band GeoTIFFs')
                if not 0 < source.width * source.height <= MAX_CELLS:
                    raise CrsError(f'Raster exceeds {MAX_CELLS} cells; crop to the site first')
                if source.transform.is_identity:
                    raise CrsError('Elevation raster needs a georeferenced pixel transform')
                if source.units[0] not in (None, '', 'm', 'metre', 'meter', 'metres', 'meters'):
                    raise CrsError('Elevation values must be in metres')
                crs = CRS(source.crs) if source.crs else None
                detail = {'width': source.width, 'height': source.height,
                          'nodata': str(source.nodata), 'transform': list(source.transform)[:6]}
        if crs and len(crs.axis_info) > 2 and crs.axis_info[2].unit_conversion_factor != 1:
            raise CrsError('Vertical values must be in metres; convert this file before uploading')
        horizontal = crs.to_2d() if crs else None
        header_epsg = horizontal.to_epsg() if horizontal else None
        code = require_epsg(epsg if epsg is not None else header_epsg)
        if horizontal and not horizontal.equals(CRS.from_epsg(code), ignore_axis_order=True):
            raise CrsError('Supplied EPSG conflicts with the file CRS')
        return {**detail, 'source_epsg': code}
    except CrsError:
        raise
    except Exception as exc:
        raise CrsError(f'Unable to read {kind} asset: {exc}') from exc


def register_asset(db, path, *, site_id, kind, filename, geom_origin, z_ref, local_zero_m, epsg=None):
    if kind not in KINDS or Path(filename).suffix.lower() not in KINDS[kind]:
        raise CrsError('Use LAS/LAZ for las, or a GeoTIFF for dsm/dtm')
    if geom_origin not in ORIGINS or z_ref not in Z_REFS:
        raise CrsError('An explicit geometry origin and supported vertical reference are required')
    if local_zero_m is None:
        if z_ref != 'LOCAL_SITE':
            raise CrsError('Non-local elevations require local_zero_m in the source vertical reference')
        local_zero_m = 0.0
    if not math.isfinite(local_zero_m) or (z_ref == 'LOCAL_SITE' and local_zero_m != 0):
        raise CrsError('local_zero_m must be finite and zero for LOCAL_SITE data')
    site = db.execute(text('SELECT z_ref FROM site WHERE id = :id'), {'id': site_id}).scalar()
    if site != 'LOCAL_SITE':
        raise CrsError('Select an existing LOCAL_SITE site')
    info = inspect_asset(path, kind, epsg)
    checksum = checksum_file(path)
    db.execute(text('SELECT pg_advisory_xact_lock(26011)'))
    existing = db.execute(text("""
        SELECT id FROM source_dataset WHERE site_id = :site AND kind = :kind
          AND checksum_sha256 = :checksum AND epsg = :epsg AND z_ref = :zref
          AND meta->>'geom_origin' = :origin
          AND (meta->>'local_zero_m')::double precision = :zero
    """), {'site': site_id, 'kind': kind, 'checksum': checksum, 'epsg': info['source_epsg'],
           'zref': z_ref, 'origin': geom_origin, 'zero': local_zero_m}).scalar()
    if existing:
        return {**get_dataset(db, existing), 'reused': True}
    meta = {**info, 'asset_name': Path(path).name, 'geom_origin': geom_origin,
            'local_zero_m': local_zero_m, 'z_unit': 'm',
            'vertical_conversion': 'local_z = source_z - declared local_zero_m; no geoid conversion'}
    dataset_id = db.execute(text("""
        INSERT INTO source_dataset (site_id, kind, filename, checksum_sha256, epsg, z_ref, meta)
        VALUES (:site, :kind, :filename, :checksum, :epsg, :zref, CAST(:meta AS jsonb)) RETURNING id
    """), {'site': site_id, 'kind': kind, 'filename': Path(filename).name, 'checksum': checksum,
           'epsg': info['source_epsg'], 'zref': z_ref, 'meta': json.dumps(meta)}).scalar_one()
    return {**get_dataset(db, dataset_id), 'reused': False}


def asset_path(source, upload_dir):
    name = source['meta'].get('asset_name')
    if not name:
        raise CrsError('Dataset is not an uploaded elevation file')
    root = Path(upload_dir).resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise CrsError('Uploaded asset is missing or outside the upload directory')
    if checksum_file(path) != source['checksum_sha256']:
        raise CrsError('Uploaded asset checksum changed; re-upload it instead of modifying source evidence')
    return path
