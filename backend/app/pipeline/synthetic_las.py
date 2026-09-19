from __future__ import annotations

from pathlib import Path

import laspy
import numpy as np
from pyproj import CRS

from app.geo import lonlat_to_utm
from app.seed import BUILDING, ORIGIN_LAT, ORIGIN_LON, PARCEL


def write_synthetic_las(out_path: Path, seed: int = 7) -> dict:
    """Authored ALS-like cloud in EPSG:32643. Ground z≈0, roof z=15, a few trees."""
    rng = np.random.default_rng(seed)
    ox, oy = lonlat_to_utm(ORIGIN_LON, ORIGIN_LAT)
    px, py, pw, ph = PARCEL
    bx, by, bw, bh = BUILDING

    def grid(x0, y0, w, h, step, z, noise=0.03):
        xs = np.arange(x0, x0 + w, step)
        ys = np.arange(y0, y0 + h, step)
        xx, yy = np.meshgrid(xs, ys)
        zz = np.full(xx.shape, z, dtype=float) + rng.normal(0, noise, xx.shape)
        return xx.ravel(), yy.ravel(), zz.ravel()

    gx, gy, gz = grid(ox + px, oy + py, pw, ph, 0.6, 0.02, 0.04)
    rx, ry, rz = grid(ox + bx, oy + by, bw, bh, 0.45, 15.05, 0.05)

    trees = []
    for tx, ty in [(ox + 6, oy + 24), (ox + 36, oy + 26), (ox + 8, oy + 6)]:
        n = 80
        ang = rng.uniform(0, 2 * np.pi, n)
        rad = rng.uniform(0, 1.8, n)
        trees.append(
            (
                tx + rad * np.cos(ang),
                ty + rad * np.sin(ang),
                rng.uniform(4.0, 9.0, n),
            )
        )
    tx = np.concatenate([t[0] for t in trees])
    ty = np.concatenate([t[1] for t in trees])
    tz = np.concatenate([t[2] for t in trees])

    x = np.concatenate([gx, rx, tx])
    y = np.concatenate([gy, ry, ty])
    z = np.concatenate([gz, rz, tz])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = laspy.LasHeader(point_format=3, version="1.4")
    header.add_crs(CRS.from_epsg(32643))
    header.offsets = [float(x.min()), float(y.min()), float(z.min())]
    header.scales = [0.001, 0.001, 0.001]
    las = laspy.LasData(header)
    las.x = x
    las.y = y
    las.z = z
    las.write(str(out_path))
    return {
        "path": str(out_path),
        "n_points": int(len(x)),
        "zmin": float(z.min()),
        "zmax": float(z.max()),
        "epsg": 32643,
        "kind": "SYNTHETIC_ALS",
    }
