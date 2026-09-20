// The API returns each spatial unit's footprint as WGS84 GeoJSON
// (ST_Transform(...,4326)). For a small (tens-of-metres) site, an
// equirectangular tangent-plane projection around a shared origin is
// accurate enough to place prisms correctly relative to each other, without
// pulling in a full projection library just for the viewer.
import * as THREE from 'three'

const EARTH_RADIUS_M = 6378137

export function makeProjector([originLon, originLat]) {
  const cosLat = Math.cos((originLat * Math.PI) / 180)
  return ([lon, lat]) => {
    const x = ((lon - originLon) * Math.PI) / 180 * EARTH_RADIUS_M * cosLat
    const y = ((lat - originLat) * Math.PI) / 180 * EARTH_RADIUS_M
    return [x, y]
  }
}

export function findOrigin(units) {
  const parcel = units.find((u) => u.su_class === 'PARCEL') || units[0]
  const ring = parcel?.geojson?.coordinates?.[0]
  if (!ring?.length) return [0, 0]
  const lon = ring.reduce((s, p) => s + p[0], 0) / ring.length
  const lat = ring.reduce((s, p) => s + p[1], 0) / ring.length
  return [lon, lat]
}

// Builds an extruded THREE.BufferGeometry for one unit's footprint, already
// rotated so height maps to world Y (three.js is Y-up) and translated so its
// base sits at world Y = zmin.
export function extrudeUnit(unit, project) {
  const ring = unit.geojson?.coordinates?.[0]
  if (!ring || ring.length < 3) return null
  const height = Math.max(unit.zmax - unit.zmin, 0.05)

  const shape = new THREE.Shape()
  ring.forEach(([lon, lat], i) => {
    const [x, y] = project([lon, lat])
    if (i === 0) shape.moveTo(x, y)
    else shape.lineTo(x, y)
  })

  const geometry = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false, curveSegments: 1 })
  geometry.rotateX(-Math.PI / 2)
  geometry.translate(0, unit.zmin, 0)
  geometry.computeVertexNormals()
  return geometry
}

export function ringToPoints(ring, project, y = 0) {
  return ring.map(([lon, lat]) => {
    const [x, z] = project([lon, lat])
    return new THREE.Vector3(x, y, z)
  })
}

export function footprintCenter(unit, project) {
  const ring = unit.geojson?.coordinates?.[0]
  if (!ring?.length) return [0, 0]
  const pts = ring.map(project)
  const x = pts.reduce((s, p) => s + p[0], 0) / pts.length
  const z = pts.reduce((s, p) => s + p[1], 0) / pts.length
  return [x, z]
}
