"""Schematic constant-height utility corridors from source centre lines."""

import math

from shapely.geometry import LineString

from app.geo import CrsError


def utility_prism(geom, props):
    diameter = props.get('diameter_m')
    width = props.get('corridor_width_m', diameter)
    for name, value in (('diameter_m', diameter), ('corridor_width_m', width)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise CrsError(f'UTILITY line requires a positive finite {name}')
    assumptions = ['Buffered centreline is a proposed corridor, not an established easement boundary']
    has_range = 'zmin' in props or 'zmax' in props
    if geom.has_z:
        if has_range or 'depth_m' in props:
            raise CrsError('Use centreline Z coordinates or height/depth properties, not both')
        zs = [p[2] for p in geom.coords]
        if not all(math.isfinite(z) for z in zs) or max(zs) - min(zs) > 0.001:
            raise CrsError('Sloping utilities must be split into constant-height segments for this prism prototype')
        center_z = sum(zs) / len(zs)
        zmin, zmax = center_z - diameter / 2, center_z + diameter / 2
    elif has_range:
        if 'depth_m' in props:
            raise CrsError('Use zmin/zmax or depth_m, not both')
        zmin, zmax = props.get('zmin'), props.get('zmax')
    else:
        depth, ground = props.get('depth_m'), props.get('ground_z_m')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (depth, ground)) or depth <= 0:
            raise CrsError('UTILITY line needs explicit zmin/zmax, constant Z, or depth_m with ground_z_m')
        zmin, zmax = ground - depth - diameter / 2, ground - depth + diameter / 2
        assumptions.append('Depth below declared ground is treated as constant along the centreline')
    line = LineString([(p[0], p[1]) for p in geom.coords])
    if line.length <= 0 or not line.is_simple:
        raise CrsError('UTILITY centreline must be nonzero and not self-crossing')
    polygon = line.buffer(width / 2, cap_style=2)
    return polygon, zmin, zmax, {'method': 'constant-height buffered prism', 'assumptions': assumptions}
