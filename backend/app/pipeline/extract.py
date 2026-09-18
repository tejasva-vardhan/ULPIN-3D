from __future__ import annotations

from pathlib import Path

import laspy
import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union


def extract_footprint(las_path: Path, height_m: float = 2.5, cell: float = 0.5) -> dict:
    """Classical nDSM extract: min-z DTM, max-z DSM, height mask, union of cells.

    Not a trained model. Output is AI_DERIVED/classical geometry, not legal title.
    """
    las = laspy.read(str(las_path))
    x, y, z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
    xmin, ymin = float(x.min()), float(y.min())
    cols = int(np.ceil((x.max() - xmin) / cell)) + 1
    rows = int(np.ceil((y.max() - ymin) / cell)) + 1
    dsm = np.full((rows, cols), -np.inf)
    dtm = np.full((rows, cols), np.inf)
    ci = np.clip(((x - xmin) / cell).astype(int), 0, cols - 1)
    ri = np.clip(((y - ymin) / cell).astype(int), 0, rows - 1)
    for i in range(len(z)):
        r, c = ri[i], ci[i]
        if z[i] > dsm[r, c]:
            dsm[r, c] = z[i]
        if z[i] < dtm[r, c]:
            dtm[r, c] = z[i]
    valid = np.isfinite(dsm) & np.isfinite(dtm)
    ndsm = np.zeros_like(dsm)
    ndsm[valid] = dsm[valid] - dtm[valid]
    mask = valid & (ndsm >= height_m)
    mask = _open(mask)

    polys = []
    for r in range(rows):
        for c in range(cols):
            if not mask[r, c]:
                continue
            x0, y0 = xmin + c * cell, ymin + r * cell
            polys.append(box(x0, y0, x0 + cell, y0 + cell))
    if not polys:
        raise ValueError("no building cells above height threshold")
    geom = unary_union(polys).buffer(cell).buffer(-cell * 0.5).simplify(cell)
    if geom.geom_type == "MultiPolygon":
        geom = max(geom.geoms, key=lambda g: g.area)
    if geom.geom_type == "Polygon" and list(geom.interiors):
        from shapely.geometry import Polygon as ShpPolygon

        geom = ShpPolygon(geom.exterior)
    return {
        "wkt": geom.wkt,
        "area_m2": float(geom.area),
        "cell_m": cell,
        "height_m": height_m,
        "method": "ndsm-min-max-morph",
        "geom_origin": "AI_DERIVED",
    }


def _open(mask: np.ndarray) -> np.ndarray:
    pad = np.pad(mask.astype(np.uint8), 1)
    out = np.zeros_like(mask, dtype=bool)
    for r in range(mask.shape[0]):
        for c in range(mask.shape[1]):
            win = pad[r : r + 3, c : c + 3]
            out[r, c] = win.sum() >= 6
    return out


def iou(a_wkt: str, b_wkt: str) -> float:
    from shapely import wkt as shapely_wkt

    a, b = shapely_wkt.loads(a_wkt), shapely_wkt.loads(b_wkt)
    inter = a.intersection(b).area
    union = a.union(b).area
    return float(inter / union) if union else 0.0
