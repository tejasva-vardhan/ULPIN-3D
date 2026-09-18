from __future__ import annotations

from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.ops import transform as shp_transform

_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
_to_wgs = Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)


class CrsError(ValueError):
    pass


def require_epsg(epsg: int | None) -> int:
    if epsg is None:
        raise CrsError("CRS missing: EPSG is required. Refusing to guess.")
    return int(epsg)


def lonlat_to_utm(lon: float, lat: float) -> tuple[float, float]:
    return _to_utm.transform(lon, lat)


def utm_to_lonlat(x: float, y: float) -> tuple[float, float]:
    return _to_wgs.transform(x, y)


def rect_from_origin(ox: float, oy: float, x0: float, y0: float, width: float, height: float) -> Polygon:
    """Axis-aligned rectangle in metres, origin at projected site origin."""
    minx, miny = ox + x0, oy + y0
    maxx, maxy = minx + width, miny + height
    return Polygon(
        [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny)]
    )


def to_wgs_geojson(poly: Polygon) -> dict:
    wgs = shp_transform(lambda x, y, z=None: (*_to_wgs.transform(x, y),), poly)
    return mapping(wgs)
