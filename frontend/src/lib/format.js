// Shared vocabulary: colors and labels for the domain enums returned by the
// API (su_class, topology_status, geom_origin), plus small formatting helpers.
// Colors are drawn from the dataviz skill's validated light-mode palette (see tailwind.config.js).

export const SU_CLASS_META = {
  PARCEL: { label: 'Parcel', color: '#52514e', short: 'PCL' },
  BUILDING: { label: 'Building', color: '#52514e', short: 'BLD' },
  FLOOR: { label: 'Floor', color: '#6b6a64', short: 'FLR' },
  UNIT: { label: 'Unit', color: '#2a78d6', short: 'UNT' },
  COMMON: { label: 'Common area', color: '#1baf7a', short: 'COM' },
  PARKING: { label: 'Parking', color: '#4a3aa7', short: 'PRK' },
  BALCONY: { label: 'Balcony', color: '#e87ba4', short: 'BAL' },
  AIR: { label: 'Air rights', color: '#eda100', short: 'AIR' },
  SUBSURFACE: { label: 'Subsurface', color: '#4f8f3f', short: 'SUB' },
  UTILITY: { label: 'Utility corridor', color: '#eb6834', short: 'UTL' },
  TRANSPORT: { label: 'Elevated transport', color: '#0f766e', short: 'TRN' },
}

export const STATUS_META = {
  VALID: { label: 'Valid', color: '#0ca30c', dot: 'bg-status-good' },
  PENDING: { label: 'Pending', color: '#898781', dot: 'bg-ink-muted' },
  DEGRADED: { label: 'Degraded', color: '#fab219', dot: 'bg-status-warning' },
  INVALID: { label: 'Invalid', color: '#d03b3b', dot: 'bg-status-critical' },
}

export const ORIGIN_META = {
  SURVEY: { label: 'Surveyed' },
  PLAN: { label: 'Authored plan' },
  AI_DERIVED: { label: 'AI-derived' },
  SYNTHETIC: { label: 'Synthetic demo' },
  MANUAL: { label: 'Manual entry' },
}

export function classMeta(cls) {
  return SU_CLASS_META[cls] || { label: cls || 'Unknown', color: '#898781', short: '—' }
}

export function statusMeta(status) {
  return STATUS_META[status] || { label: status || 'Unknown', color: '#898781', dot: 'bg-ink-muted' }
}

export function formatNumber(value, opts = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-IN', opts).format(value)
}

export function formatCompact(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

export function formatMeters(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${Number(value).toFixed(digits)} m`
}

export function formatVolume(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${formatNumber(value, { maximumFractionDigits: 1 })} m³`
}

export function formatPercent(fraction, digits = 0) {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) return '—'
  return `${(fraction * 100).toFixed(digits)}%`
}

export function formatDate(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return String(value)
  }
}

export function truncateId(id, length = 8) {
  if (!id) return '—'
  return String(id).slice(0, length)
}
