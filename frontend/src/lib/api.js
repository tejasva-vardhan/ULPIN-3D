const API_BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000').replace(/\/$/, '')

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

function qs(params = {}) {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  if (!entries.length) return ''
  return '?' + new URLSearchParams(entries).toString()
}

async function request(path, { method = 'GET', body, headers, raw = false } = {}) {
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body !== undefined && !raw ? { 'Content-Type': 'application/json', ...headers } : headers,
      body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
    })
  } catch (networkError) {
    throw new ApiError(
      `Could not reach the Stratum API at ${API_BASE}. Is the backend running?`,
      0,
      networkError.message,
    )
  }

  const contentType = res.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await res.json().catch(() => null) : null

  if (!res.ok) {
    const detail = payload?.detail || res.statusText || 'Request failed'
    throw new ApiError(typeof detail === 'string' ? detail : JSON.stringify(detail), res.status, payload)
  }
  return payload
}

export { API_BASE, ApiError }
export const eventsUrl = () => `${API_BASE}/events`

// --- health & demo -------------------------------------------------------

export const getHealth = () => request('/health')
export const seedDemo = () => request('/demo/seed', { method: 'POST' })
export const seedDegraded = () => request('/demo/degraded-no-plans', { method: 'POST' })
export const fixOverlap = () => request('/demo/fix-overlap', { method: 'POST' })
export const demoProcessBuilding = () => request('/demo/process/building', { method: 'POST' })

// --- sites & datasets ------------------------------------------------------

export const listSites = () => request('/sites')
export const createSite = (payload) => request('/sites', { method: 'POST', body: payload })
export const listDatasets = () => request('/datasets')
export const getDataset = (id) => request(`/datasets/${id}`)
export const createDataset = (payload) => request('/datasets', { method: 'POST', body: payload })
export const processDataset = (id) => request(`/datasets/${id}/process`, { method: 'POST' })

export async function uploadElevationFile({ file, siteId, kind, geomOrigin, zRef, localZeroM, epsg }) {
  const query = qs({
    site_id: siteId,
    kind,
    filename: file.name,
    geom_origin: geomOrigin,
    z_ref: zRef,
    local_zero_m: localZeroM,
    epsg,
  })
  return request(`/datasets/files${query}`, {
    method: 'POST',
    raw: true,
    body: file,
    headers: { 'Content-Type': 'application/octet-stream' },
  })
}

// --- spatial units -----------------------------------------------------

// The API sends each unit's footprint as a raw ST_AsGeoJSON() string (not a
// parsed object) in the `geojson` field. Parse it here, once, so every
// consumer (the 3D viewer, record cards, ...) can treat `unit.geojson` as a
// real GeoJSON geometry object.
function parseUnitGeojson(unit) {
  if (typeof unit?.geojson === 'string') {
    try {
      return { ...unit, geojson: JSON.parse(unit.geojson) }
    } catch {
      return { ...unit, geojson: null }
    }
  }
  return unit
}

export const listUnits = (siteId) =>
  request(`/spatial-units${qs({ site_id: siteId })}`).then((r) => ({
    ...r,
    units: (r.units || []).map(parseUnitGeojson),
  }))
export const getUnitByCode = (code, siteId) =>
  request(`/spatial-units/by-code/${code}${qs({ site_id: siteId })}`).then(parseUnitGeojson)
export const listUnitVersions = (code, siteId) =>
  request(`/spatial-units/by-code/${code}/versions${qs({ site_id: siteId })}`)
export const getParcel = () => request('/parcel')
export const getBuildingSummary = () => request('/building')
export const getFloors = () => request('/floors')

// --- rights --------------------------------------------------------------

export const listRRR = (siteId) => request(`/rrr${qs({ site_id: siteId })}`)
export const listParties = () => request('/parties')
export const listBaunits = () => request('/baunits')
export const createParty = (payload) => request('/parties', { method: 'POST', body: payload })
export const createBaunit = (payload) => request('/baunits', { method: 'POST', body: payload })
export const linkBaunit = (baunitId, payload) => request(`/baunits/${baunitId}/link`, { method: 'POST', body: payload })
export const createRRR = (payload) => request('/rrr', { method: 'POST', body: payload })

// --- review / lifecycle --------------------------------------------------

export const postReview = (localCode, payload, siteId) =>
  request(`/spatial-units/${localCode}/review${qs({ site_id: siteId })}`, { method: 'POST', body: payload })
export const getReviewHistory = (localCode, siteId) =>
  request(`/spatial-units/${localCode}/review-history${qs({ site_id: siteId })}`)
export const getReviewsByUnitId = (spatialUnitId) => request(`/reviews/${spatialUnitId}`)
export const withdrawUnit = (localCode, payload, siteId) =>
  request(`/units/${localCode}/withdraw${qs({ site_id: siteId })}`, { method: 'POST', body: payload })
export const issueUnit = (localCode, siteId) => request(`/issue/${localCode}${qs({ site_id: siteId })}`, { method: 'POST' })
export const newUnitVersion = (localCode, siteId) =>
  request(`/units/${localCode}/new-version${qs({ site_id: siteId })}`, { method: 'POST' })

// --- records ---------------------------------------------------------------

export const getRecordByCode = (localCode, siteId) => request(`/record/${localCode}${qs({ site_id: siteId })}`)
export const getRecordByUnitId = (spatialUnitId) => request(`/records/${spatialUnitId}`)
export const recordHtmlUrl = (localCode, siteId) => `${API_BASE}/record/${localCode}/html${qs({ site_id: siteId })}`

// --- elevation pipeline ---------------------------------------------------

export const processBuilding = (payload) => request('/process/building', { method: 'POST', body: payload })
export const getRun = (runId) => request(`/runs/${runId}`)

// --- validation ------------------------------------------------------------

export const runValidation = () => request('/validate', { method: 'POST' })
export const getValidationLatest = () => request('/validation/latest')
export const getValidationRun = (runId) => request(`/validation/${runId}`)

// --- exports -----------------------------------------------------------

export const modelGltfUrl = () => `${API_BASE}/model.gltf`
export const exportCityGmlUrl = (siteId, buildingId) =>
  `${API_BASE}/export/citygml${qs({ site_id: siteId, building_id: buildingId })}`
export const exportGeoJsonUrl = (siteId) => `${API_BASE}/export/geojson${qs({ site_id: siteId })}`
