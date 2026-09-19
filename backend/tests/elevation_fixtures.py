"""Small authored elevation files for repeatable tests; not survey evidence."""

import laspy
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import from_origin


def cloud_file(path, *, epsg=32643, classified=True, header_crs=True):
    gx, gy = np.meshgrid(np.arange(0, 30, 0.5), np.arange(0, 20, 0.5))
    gx, gy = gx.ravel(), gy.ravel()
    # Airborne ground samples do not exist underneath the roof.
    outside = ~((gx >= 2) & (gx < 22) & (gy >= 2) & (gy < 12))
    rx, ry = np.meshgrid(np.arange(2, 22, 0.5), np.arange(2, 12, 0.5))
    rx, ry = rx.ravel(), ry.ravel()
    x = np.concatenate([gx[outside], rx])
    y = np.concatenate([gy[outside], ry])
    z = 430 + 0.01*x + 0.02*y
    z[len(gx[outside]):] += 9
    classes = np.concatenate([np.full(outside.sum(), 2), np.full(len(rx), 6)]).astype('uint8')
    x, y = x+500000, y+2050000
    if epsg != 32643:
        x, y = Transformer.from_crs(32643, epsg, always_xy=True).transform(x, y)
    header = laspy.LasHeader(point_format=3, version='1.2')
    if header_crs:
        header.add_crs(CRS.from_epsg(epsg))
    header.offsets = [float(np.min(x)), float(np.min(y)), 430]
    header.scales = [1e-9 if epsg == 4326 else 0.001, 1e-9 if epsg == 4326 else 0.001, 0.001]
    cloud = laspy.LasData(header)
    cloud.x, cloud.y, cloud.z = x, y, z
    cloud.classification = classes if classified else np.zeros(len(x), dtype='uint8')
    cloud.write(path)
    return path


def raster_file(path, *, surface=True, resolution=1, nodata_pixel=False, empty=False):
    width, height = int(30/resolution), int(20/resolution)
    values = np.full((height, width), 430, dtype='float32')
    if surface:
        values[int(8/resolution):int(18/resolution), int(2/resolution):int(22/resolution)] += 9
    if nodata_pixel:
        values[int(10/resolution), int(3/resolution)] = -9999
    if empty:
        values[:] = -9999
    with rasterio.open(path, 'w', driver='GTiff', width=width, height=height, count=1,
                       dtype='float32', crs='EPSG:32643', nodata=-9999,
                       transform=from_origin(500000, 2050020, resolution, resolution)) as dst:
        dst.write(values, 1)
    return path
