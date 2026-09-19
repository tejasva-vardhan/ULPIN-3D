"""Classical, site-scale height and footprint estimates from external elevations."""

import laspy
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import geometry_mask, shapes
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely import intersects_xy
from shapely.geometry import shape, mapping

from app.geo import CrsError
from app.pipeline.assets import MAX_CELLS, MAX_POINTS


def _footprint(mask, transform, parcel):
    candidates = []
    for geometry, value in shapes(mask.astype('uint8'), mask=mask, transform=transform):
        if value != 1:
            continue
        polygon = shape(geometry).intersection(parcel)
        parts = list(polygon.geoms) if polygon.geom_type == 'MultiPolygon' else [polygon]
        candidates.extend(p for p in parts if p.geom_type == 'Polygon' and p.area > 0)
    if not candidates:
        raise CrsError('No elevated building candidate found in this parcel')
    return max(candidates, key=lambda p: p.area), len(candidates)


def measure_cloud(path, epsg, local_zero_m, parcel, *, cell_m=0.5, threshold_m=2.5, footprint=None):
    with laspy.open(path) as reader:
        if not 0 < reader.header.point_count <= MAX_POINTS:
            raise CrsError('Point cloud is empty or exceeds the site-scale processing limit')
        cloud = reader.read()
    x, y, z = np.asarray(cloud.x), np.asarray(cloud.y), np.asarray(cloud.z) - local_zero_m
    x, y = Transformer.from_crs(epsg, 32643, always_xy=True).transform(x, y, errcheck=True)
    x, y = np.asarray(x), np.asarray(y)
    classes = np.asarray(cloud.classification)
    finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    inside = finite & intersects_xy(parcel, x, y)
    x, y, z, classes = x[inside], y[inside], z[inside], classes[inside]
    if len(z) < 6:
        raise CrsError('Insufficient finite point-cloud samples inside the parcel')
    assumptions = []
    ground = classes == 2
    if ground.sum() < 3:
        ground = z <= np.percentile(z, 15)
        assumptions.append('Ground estimated from the lowest 15% of points; no reliable ground classification')
    if ground.sum() < 3:
        raise CrsError('Insufficient ground samples for height estimation')
    x0, y0 = float(np.mean(x[ground])), float(np.mean(y[ground]))
    design = np.column_stack((x[ground] - x0, y[ground] - y0, np.ones(ground.sum())))
    fit, _, rank, _ = np.linalg.lstsq(design, z[ground], rcond=None)
    if rank < 3:
        fit = np.array([0.0, 0.0, np.median(z[ground])])
        assumptions.append('Ground samples do not constrain a plane; median ground level used')
    predicted_ground = fit[0] * (x - x0) + fit[1] * (y - y0) + fit[2]
    ground_rmse = float(np.sqrt(np.mean((predicted_ground[ground] - z[ground]) ** 2)))
    elevated = (z - predicted_ground) >= threshold_m
    classified = (classes == 6) & elevated
    if classified.sum() >= 3:
        candidates = classified
        method = 'classified-building-points'
    else:
        candidates = elevated & ~np.isin(classes, [2, 3, 4, 5, 7, 9, 18])
        method = 'ground-plane-height-threshold'
        assumptions.append('Unclassified elevated surfaces can include vegetation or other structures')
    if footprint is None:
        if candidates.sum() < 3:
            raise CrsError('Insufficient elevated building samples')
        xmin, ymax = float(x.min()), float(y.max())
        width = int(np.floor((x.max() - xmin) / cell_m)) + 1
        height = int(np.floor((ymax - y.min()) / cell_m)) + 1
        if width * height > MAX_CELLS:
            raise CrsError('Point-cloud grid is too large; crop the file or increase cell_m')
        mask = np.zeros((height, width), dtype=bool)
        cols = np.floor((x[candidates] - xmin) / cell_m).astype(int)
        rows = np.floor((ymax - y[candidates]) / cell_m).astype(int)
        mask[rows, cols] = True
        footprint, count = _footprint(mask, from_origin(xmin, ymax, cell_m, cell_m), parcel)
        if count > 1:
            assumptions.append(f'Largest of {count} connected elevated candidates selected')
    else:
        count = 1
        method += '-plan-footprint'
    roof = candidates & intersects_xy(footprint, x, y)
    if roof.sum() < 3:
        raise CrsError('Insufficient roof samples within the selected footprint')
    center = footprint.centroid
    ground_z = float(fit[0] * (center.x - x0) + fit[1] * (center.y - y0) + fit[2])
    height_m = float(np.percentile((z - predicted_ground)[roof], 95))
    if height_m <= 0 or not np.isfinite(height_m):
        raise CrsError('Derived building height is invalid')
    assumptions.append('Building height is the 95th percentile above a local ground plane')
    return {'footprint': footprint, 'ground_z': ground_z, 'roof_z': ground_z + height_m,
            'height_m': height_m, 'method': method, 'assumptions': assumptions,
            'point_count': len(z), 'roof_samples': int(roof.sum()), 'ground_rmse_m': ground_rmse,
            'candidate_count': count, 'confidence': 0.7 if classified.sum() >= 3 and ground_rmse < 0.5 else 0.35,
            'confidence_kind': 'heuristic, not a calibrated probability'}


def measure_rasters(dsm_path, dtm_path, dsm_meta, dtm_meta, parcel, *, threshold_m=2.5, footprint=None):
    with rasterio.open(dsm_path) as dsm, rasterio.open(dtm_path) as dtm:
        dst_transform, width, height = calculate_default_transform(
            dsm_meta['source_epsg'], 32643, dsm.width, dsm.height, *dsm.bounds)
        if not 0 < width * height <= MAX_CELLS:
            raise CrsError('Reprojected raster grid exceeds the site-scale limit')
        aligned = []
        for source, meta in ((dsm, dsm_meta), (dtm, dtm_meta)):
            values = source.read(1, masked=True).astype('float64').filled(np.nan)
            values = values * source.scales[0] + source.offsets[0] - meta['local_zero_m']
            values[~np.isfinite(values)] = np.nan
            target = np.full((height, width), np.nan, dtype='float64')
            reproject(values, target, src_transform=source.transform,
                      src_crs=meta['source_epsg'], src_nodata=np.nan,
                      dst_transform=dst_transform, dst_crs=32643, dst_nodata=np.nan,
                      resampling=Resampling.bilinear)
            aligned.append(target)
    surface, ground = aligned
    parcel_mask = geometry_mask([mapping(parcel)], (height, width), dst_transform, invert=True)
    valid = parcel_mask & np.isfinite(surface) & np.isfinite(ground)
    if valid.sum() < 4:
        raise CrsError('DSM and DTM have insufficient overlapping valid coverage inside the parcel')
    ndsm = surface - ground
    assumptions = ['DSM and DTM aligned to the DSM grid in EPSG:32643 using bilinear resampling']
    if footprint is None:
        footprint, count = _footprint(valid & (ndsm >= threshold_m), dst_transform, parcel)
        if count > 1:
            assumptions.append(f'Largest of {count} connected elevated candidates selected')
    else:
        count = 1
    selected = geometry_mask([mapping(footprint)], (height, width), dst_transform, invert=True) & valid
    if selected.sum() < 4:
        raise CrsError('Insufficient valid elevation pixels within the building footprint')
    height_m = float(np.percentile(ndsm[selected], 95))
    ground_z = float(np.median(ground[selected]))
    if not np.isfinite(height_m) or height_m < threshold_m:
        raise CrsError('No building height above the selected threshold')
    coverage = float(valid.sum() / max(int(parcel_mask.sum()), 1))
    assumptions.extend(['Height is the 95th percentile of DSM minus DTM; ground is the footprint median',
                        'Elevated raster surfaces can include trees; inspect the candidate footprint'])
    return {'footprint': footprint, 'ground_z': ground_z, 'roof_z': ground_z + height_m,
            'height_m': height_m, 'method': 'aligned-dsm-minus-dtm', 'assumptions': assumptions,
            'valid_pixels': int(selected.sum()), 'coverage_fraction': coverage, 'candidate_count': count,
            'confidence': 0.6 if coverage >= 0.8 else 0.3,
            'confidence_kind': 'heuristic, not a calibrated probability'}
