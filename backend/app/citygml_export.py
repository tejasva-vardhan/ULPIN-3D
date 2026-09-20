from __future__ import annotations

from xml.sax.saxutils import escape

from shapely import wkt as shapely_wkt


def building_lod1_citygml(row: dict) -> str:
    """CityGML 2.0 LOD1 physical building. Not LADM, not legal title, not official ULPIN."""
    poly = shapely_wkt.loads(row["wkt"])
    ring = list(poly.exterior.coords)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    z0, z1 = float(row["zmin"]), float(row["zmax"])
    gid = _gml_id(row.get("local_code") or "B1")
    patches = []
    patches.append(_patch(f"{gid}-bottom", list(reversed(ring)), z0))
    patches.append(_patch(f"{gid}-top", ring, z1))
    for i in range(len(ring) - 1):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[i + 1][0], ring[i + 1][1]
        wall = [(x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1), (x0, y0, z0)]
        patches.append(_pos_patch(f"{gid}-w{i}", wall))
    members = "\n".join(f"              <gml:surfaceMember>\n{p}\n              </gml:surfaceMember>" for p in patches)
    display = escape(str(row.get("display_id") or ""))
    parent = escape(str(row.get("parent_ulpin") or ""))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"
  xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
  xmlns:gen="http://www.opengis.net/citygml/generics/2.0"
  xmlns:gml="http://www.opengis.net/gml"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.opengis.net/citygml/building/2.0 http://schemas.opengis.net/citygml/building/2.0/building.xsd">
  <gml:name>Stratum LOD1 physical export</gml:name>
  <gml:description>Physical CityGML LOD1 only. Legal 3D spaces stay in PostGIS (LADM-aligned). Proposed 3D ULPIN is not an official DoLR identifier. Not cadastral title.</gml:description>
  <core:cityObjectMember>
    <bldg:Building gml:id="{gid}">
      <gml:name>{escape(str(row.get("local_code") or "B1"))}</gml:name>
      <gml:description>Building envelope. geom_origin={escape(str(row.get("geom_origin") or ""))}</gml:description>
      <gen:stringAttribute name="parent_ulpin">
        <gen:value>{parent}</gen:value>
      </gen:stringAttribute>
      <gen:stringAttribute name="proposed_3d_ulpin_display">
        <gen:value>{display}</gen:value>
      </gen:stringAttribute>
      <gen:stringAttribute name="not_official_ulpin">
        <gen:value>true</gen:value>
      </gen:stringAttribute>
      <bldg:measuredHeight uom="m">{z1 - z0:.3f}</bldg:measuredHeight>
      <bldg:lod1Solid>
        <gml:Solid srsName="EPSG:32643" srsDimension="3">
          <gml:exterior>
            <gml:CompositeSurface>
{members}
            </gml:CompositeSurface>
          </gml:exterior>
        </gml:Solid>
      </bldg:lod1Solid>
    </bldg:Building>
  </core:cityObjectMember>
</core:CityModel>
"""


def _gml_id(code: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(code))
    return "bldg-" + cleaned


def _patch(gid: str, ring_xy, z: float) -> str:
    pos = " ".join(f"{p[0]:.4f} {p[1]:.4f} {z:.4f}" for p in ring_xy)
    return _pos_xml(gid, pos)


def _pos_patch(gid: str, xyz) -> str:
    pos = " ".join(f"{x:.4f} {y:.4f} {z:.4f}" for x, y, z in xyz)
    return _pos_xml(gid, pos)


def _pos_xml(gid: str, pos: str) -> str:
    return (
        f'                <gml:Polygon gml:id="{gid}" srsName="EPSG:32643" srsDimension="3">\n'
        f"                  <gml:exterior><gml:LinearRing><gml:posList srsDimension=\"3\">{pos}</gml:posList></gml:LinearRing></gml:exterior>\n"
        f"                </gml:Polygon>"
    )
