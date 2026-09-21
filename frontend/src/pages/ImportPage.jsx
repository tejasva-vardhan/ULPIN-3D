import React, { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { FileJson, UploadCloud, Layers, Play, CheckCircle2, FileUp, Satellite, Network } from 'lucide-react'
import { Card, Button, Field, inputClass, EmptyState } from '../components/ui/primitives.jsx'
import { useToast } from '../lib/ToastContext.jsx'
import {
  listDatasets,
  createDataset,
  processDataset,
  uploadElevationFile,
  processBuilding,
  listSites,
  getUnitByCode,
  getValidationRun,
} from '../lib/api.js'
import clsx from '../lib/clsx.js'

const TABS = [
  { key: 'geojson', label: 'Property GeoJSON', icon: FileJson },
  { key: 'elevation', label: 'Elevation → building', icon: Satellite },
  { key: 'utility', label: 'Underground utility', icon: Network },
]

export default function ImportPage({ siteId }) {
  const [tab, setTab] = useState('geojson')
  return (
    <div className="space-y-6">
      <div className="flex gap-2 rounded-xl border border-hairline bg-black/[0.02] p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              'flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition',
              tab === t.key ? 'bg-accent-blue/15 text-accent-blue' : 'text-ink-secondary hover:text-ink-primary',
            )}
          >
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>
      {tab === 'geojson' && <GeoJsonImport siteId={siteId} />}
      {tab === 'elevation' && <ElevationImport siteId={siteId} />}
      {tab === 'utility' && <UtilityImport siteId={siteId} />}
    </div>
  )
}

// --- shared: site picker fallback ------------------------------------------

function useResolvedSite(siteId) {
  const [sites, setSites] = useState([])
  const [chosen, setChosen] = useState(siteId)
  useEffect(() => {
    listSites().then((r) => setSites(r.sites || [])).catch(() => setSites([]))
  }, [])
  useEffect(() => setChosen(siteId), [siteId])
  return { sites, chosen, setChosen }
}

function SitePicker({ sites, value, onChange }) {
  return (
    <Field label="Site" required>
      <select className={inputClass} value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Select a site…</option>
        {sites.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </Field>
  )
}

// --- GeoJSON property import -------------------------------------------

function GeoJsonImport({ siteId }) {
  const toast = useToast()
  const { sites, chosen, setChosen } = useResolvedSite(siteId)
  const [datasets, setDatasets] = useState(null)
  const [file, setFile] = useState(null)
  const [geojson, setGeojson] = useState(null)
  const [kind, setKind] = useState('floor_plans')
  const [epsg, setEpsg] = useState('32643')
  const [origin, setOrigin] = useState('PLAN')
  const [busy, setBusy] = useState(false)
  const [processing, setProcessing] = useState(null)
  const inputRef = useRef(null)

  const loadDatasets = useCallback(() => {
    listDatasets()
      .then((r) => setDatasets(r.datasets))
      .catch(() => setDatasets([]))
  }, [])
  useEffect(() => loadDatasets(), [loadDatasets])

  async function onFile(e) {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    try {
      const text = await f.text()
      const parsed = JSON.parse(text)
      setGeojson(parsed)
    } catch {
      toast.error('That file is not valid JSON.')
      setGeojson(null)
    }
  }

  async function submit() {
    if (!chosen) return toast.warning('Choose a site first.')
    if (!geojson) return toast.warning('Choose a GeoJSON file to import.')
    setBusy(true)
    try {
      const res = await createDataset({
        kind,
        geojson,
        epsg: Number(epsg),
        site_id: chosen,
        filename: file?.name,
        geom_origin: origin,
      })
      toast.success(`Imported ${geojson.features?.length ?? geojson.type === 'Feature' ? 1 : '?'} feature(s) as ${res.kind}.`, {
        title: res.reused ? 'Dataset already imported' : 'Dataset imported',
      })
      setFile(null)
      setGeojson(null)
      if (inputRef.current) inputRef.current.value = ''
      loadDatasets()
    } catch (err) {
      toast.error(err.message, { title: 'Import failed' })
    } finally {
      setBusy(false)
    }
  }

  async function handleProcess(id) {
    setProcessing(id)
    try {
      const res = await processDataset(id)
      toast.success(`${res.count} spatial unit(s) constructed, ${res.extruded_solids} solids extruded.`, {
        title: 'Dataset processed',
      })
      loadDatasets()
    } catch (err) {
      toast.error(err.message, { title: 'Processing failed' })
    } finally {
      setProcessing(null)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
      <Card className="space-y-3 p-5 lg:col-span-2">
        <h2 className="text-sm font-semibold text-ink-primary">Import property GeoJSON</h2>
        <p className="text-xs text-ink-secondary">
          Each Polygon feature needs <code className="font-mono text-accent-blue">local_code</code>,{' '}
          <code className="font-mono text-accent-blue">su_class</code>, <code className="font-mono text-accent-blue">zmin</code>/
          <code className="font-mono text-accent-blue">zmax</code> and, for non-parcels,{' '}
          <code className="font-mono text-accent-blue">parent_code</code>.
        </p>
        <SitePicker sites={sites} value={chosen} onChange={setChosen} />
        <Field label="GeoJSON file" required>
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-hairline bg-black/[0.02] px-3 py-6 text-xs text-ink-muted transition hover:border-accent-blue/40 hover:text-ink-secondary">
            <UploadCloud size={16} />
            {file ? file.name : 'Click to choose a .geojson / .json file'}
            <input ref={inputRef} type="file" accept=".geojson,.json,application/geo+json" className="hidden" onChange={onFile} />
          </label>
        </Field>
        {geojson && (
          <p className="flex items-center gap-1.5 text-[11px] text-status-good">
            <CheckCircle2 size={12} /> Parsed {geojson.features?.length ?? 1} feature(s)
          </p>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Dataset kind">
            <input className={inputClass} value={kind} onChange={(e) => setKind(e.target.value)} />
          </Field>
          <Field label="Source EPSG" required>
            <input className={`${inputClass} font-mono`} value={epsg} onChange={(e) => setEpsg(e.target.value)} />
          </Field>
        </div>
        <Field label="Default geometry origin">
          <select className={inputClass} value={origin} onChange={(e) => setOrigin(e.target.value)}>
            {['SURVEY', 'PLAN', 'AI_DERIVED', 'SYNTHETIC', 'MANUAL'].map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </Field>
        <Button onClick={submit} loading={busy} icon={UploadCloud} className="w-full">
          Import dataset
        </Button>
      </Card>

      <div className="lg:col-span-3">
        <h2 className="mb-3 text-sm font-semibold text-ink-primary">Imported datasets</h2>
        {datasets === null ? (
          <p className="text-xs text-ink-muted">Loading…</p>
        ) : datasets.length === 0 ? (
          <EmptyState icon={FileJson} title="No datasets yet" description="Import a GeoJSON file to see it listed here." />
        ) : (
          <div className="space-y-2.5">
            {datasets.map((d, i) => {
              const processed = Boolean(d.meta?.processed_unit_ids)
              return (
                <motion.div key={d.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
                  <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink-primary">{d.filename}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-ink-muted">
                        {d.kind} · EPSG:{d.epsg} · {d.meta?.feature_count ?? '?'} feature(s)
                      </p>
                    </div>
                    {processed ? (
                      <span className="flex items-center gap-1.5 rounded-full bg-status-good/10 px-2.5 py-1 text-[11px] font-medium text-status-good">
                        <CheckCircle2 size={12} /> processed
                      </span>
                    ) : (
                      <Button variant="ghost" loading={processing === d.id} onClick={() => handleProcess(d.id)} icon={Play}>
                        Process
                      </Button>
                    )}
                  </Card>
                </motion.div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// --- Underground utility centre-line -----------------------------------

const EXAMPLE_UTILITY = {
  type: 'Feature',
  geometry: {
    type: 'LineString',
    coordinates: [[374142, 2046745], [374157, 2046745], [374176, 2046764]],
  },
  properties: {},
}

function UtilityImport({ siteId }) {
  const toast = useToast()
  const { sites, chosen, setChosen } = useResolvedSite(siteId)
  const [file, setFile] = useState(null)
  const [line, setLine] = useState(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const inputRef = useRef(null)
  const [form, setForm] = useState({
    localCode: 'UTIL-01',
    parentCode: 'LOT',
    utilityType: 'WATER',
    diameterM: '0.6',
    corridorWidthM: '1.0',
    depthM: '1.5',
    groundZM: '0',
    epsg: '32643',
    origin: 'SURVEY',
  })

  function readLine(raw, label) {
    const features = raw?.type === 'FeatureCollection' ? raw.features : [raw]
    if (features.length !== 1 || features[0]?.type !== 'Feature' || features[0]?.geometry?.type !== 'LineString') {
      throw new Error('Choose GeoJSON containing exactly one LineString feature.')
    }
    if (!Array.isArray(features[0].geometry.coordinates) || features[0].geometry.coordinates.length < 2) {
      throw new Error('The utility centre-line needs at least two coordinates.')
    }
    setLine(features[0])
    setFile(label)
    setResult(null)
  }

  async function onFile(event) {
    const selected = event.target.files?.[0]
    if (!selected) return
    try {
      readLine(JSON.parse(await selected.text()), selected.name)
    } catch (error) {
      setLine(null)
      setFile(null)
      toast.error(error.message, { title: 'Invalid utility file' })
    }
  }

  async function submit() {
    if (!chosen) return toast.warning('Choose a site first.')
    if (!line) return toast.warning('Choose a utility centre-line or load the example.')
    const diameter = Number(form.diameterM)
    const width = Number(form.corridorWidthM)
    const depth = Number(form.depthM)
    const ground = Number(form.groundZM)
    if (!form.localCode || !form.parentCode) return toast.warning('Utility and parent codes are required.')
    if (![diameter, width, depth, ground].every(Number.isFinite) || diameter <= 0 || width <= 0 || depth <= 0) {
      return toast.warning('Diameter, corridor width, depth, and ground elevation must be valid metre values.')
    }
    setBusy(true)
    try {
      const feature = {
        ...line,
        id: form.localCode,
        properties: {
          ...(line.properties || {}),
          local_code: form.localCode,
          parent_code: form.parentCode,
          su_class: 'UTILITY',
          utility_type: form.utilityType,
          diameter_m: diameter,
          corridor_width_m: width,
          depth_m: depth,
          ground_z_m: ground,
          geom_origin: form.origin,
          requires_review: true,
        },
      }
      const dataset = await createDataset({
        kind: 'underground_utilities',
        geojson: { type: 'FeatureCollection', features: [feature] },
        epsg: Number(form.epsg),
        site_id: chosen,
        filename: file || `${form.localCode}.geojson`,
        geom_origin: form.origin,
      })
      const processed = await processDataset(dataset.id)
      const [unit, validation] = await Promise.all([
        getUnitByCode(form.localCode, chosen),
        getValidationRun(processed.validation_run_id),
      ])
      const findings = (validation.results || []).filter((finding) =>
        processed.unit_ids.includes(finding.spatial_unit_id) && !finding.passed)
      setResult({ dataset, processed, unit, findings })
      toast.success('The centre-line was converted into a review-required 3D utility corridor.', {
        title: 'Utility volume created',
      })
    } catch (error) {
      toast.error(error.message, { title: 'Utility import failed' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card className="space-y-3 p-5">
        <h2 className="text-sm font-semibold text-ink-primary">Import a utility centre-line</h2>
        <p className="text-xs text-ink-secondary">
          A 2D LineString is buffered horizontally and placed below the declared ground elevation. The resulting corridor remains review-required.
        </p>
        <SitePicker sites={sites} value={chosen} onChange={setChosen} />
        <Field label="Centre-line GeoJSON" required>
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-hairline bg-black/[0.02] px-3 py-5 text-xs text-ink-muted transition hover:border-accent-blue/40">
            <UploadCloud size={16} /> {file || 'Choose one LineString feature'}
            <input ref={inputRef} type="file" accept=".geojson,.json,application/geo+json" className="hidden" onChange={onFile} />
          </label>
        </Field>
        <Button variant="ghost" onClick={() => {
          readLine(EXAMPLE_UTILITY, 'Synthetic example centre-line')
          setForm((current) => ({ ...current, origin: 'SYNTHETIC' }))
        }} className="w-full">
          Load synthetic example
        </Button>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Utility local_code" required>
            <input className={`${inputClass} font-mono`} value={form.localCode} onChange={(e) => setForm({ ...form, localCode: e.target.value })} />
          </Field>
          <Field label="Parent parcel code" required>
            <input className={`${inputClass} font-mono`} value={form.parentCode} onChange={(e) => setForm({ ...form, parentCode: e.target.value })} />
          </Field>
          <Field label="Utility type">
            <select className={inputClass} value={form.utilityType} onChange={(e) => setForm({ ...form, utilityType: e.target.value })}>
              {['WATER', 'SEWER', 'GAS', 'POWER', 'TELECOM', 'OTHER'].map((type) => <option key={type}>{type}</option>)}
            </select>
          </Field>
          <Field label="Source EPSG">
            <input className={`${inputClass} font-mono`} value={form.epsg} onChange={(e) => setForm({ ...form, epsg: e.target.value })} />
          </Field>
          <Field label="Pipe diameter (m)">
            <input className={`${inputClass} font-mono`} type="number" min="0.01" step="0.1" value={form.diameterM} onChange={(e) => setForm({ ...form, diameterM: e.target.value })} />
          </Field>
          <Field label="Corridor width (m)" hint="Proposed right-of-way envelope">
            <input className={`${inputClass} font-mono`} type="number" min="0.01" step="0.1" value={form.corridorWidthM} onChange={(e) => setForm({ ...form, corridorWidthM: e.target.value })} />
          </Field>
          <Field label="Centre depth (m)" hint="Below declared ground">
            <input className={`${inputClass} font-mono`} type="number" min="0.01" step="0.1" value={form.depthM} onChange={(e) => setForm({ ...form, depthM: e.target.value })} />
          </Field>
          <Field label="Ground elevation (m)">
            <input className={`${inputClass} font-mono`} type="number" step="0.1" value={form.groundZM} onChange={(e) => setForm({ ...form, groundZM: e.target.value })} />
          </Field>
        </div>
        <Field label="Geometry origin">
          <select className={inputClass} value={form.origin} onChange={(e) => setForm({ ...form, origin: e.target.value })}>
            {['SURVEY', 'PLAN', 'MANUAL', 'SYNTHETIC'].map((origin) => <option key={origin}>{origin}</option>)}
          </select>
        </Field>
        <Button onClick={submit} loading={busy} icon={Network} className="w-full">Create 3D utility corridor</Button>
      </Card>

      <Card className="space-y-3 p-5">
        <h2 className="text-sm font-semibold text-ink-primary">Construction result</h2>
        {!result ? (
          <EmptyState icon={Network} title="No corridor created yet" description="Import a centre-line to see its vertical range, volume, and validation findings." />
        ) : (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-3 text-xs">
            <div className="rounded-lg border border-status-warning/25 bg-status-warning/[0.06] p-3">
              <p className="font-semibold text-ink-primary">Review required before issuance</p>
              <p className="mt-1 text-ink-secondary">Buffered centre-lines are proposed corridors and do not establish an easement boundary.</p>
            </div>
            <dl className="grid grid-cols-2 gap-3 rounded-lg bg-black/[0.03] p-3">
              <div><dt className="text-ink-muted">Local code</dt><dd className="font-mono text-ink-primary">{result.unit.local_code}</dd></div>
              <div><dt className="text-ink-muted">Topology</dt><dd className="font-mono text-ink-primary">{result.unit.topology_status}</dd></div>
              <div><dt className="text-ink-muted">Vertical range</dt><dd className="font-tabular text-ink-primary">{result.unit.zmin.toFixed(2)} to {result.unit.zmax.toFixed(2)} m</dd></div>
              <div><dt className="text-ink-muted">Volume</dt><dd className="font-tabular text-ink-primary">{result.unit.volume_m3?.toFixed(2)} m³</dd></div>
            </dl>
            <div>
              <p className="font-medium text-ink-primary">Validation findings</p>
              {result.findings.length === 0 ? (
                <p className="mt-1 text-status-good">No geometry conflicts detected. Human review is still required.</p>
              ) : (
                <ul className="mt-2 space-y-1 text-ink-secondary">
                  {result.findings.map((finding, index) => (
                    <li key={`${finding.rule_code}-${index}`}><span className="font-mono">{finding.rule_code}</span> · {finding.severity}</li>
                  ))}
                </ul>
              )}
            </div>
          </motion.div>
        )}
      </Card>
    </div>
  )
}

// --- Elevation → building pipeline -------------------------------------

function ElevationImport({ siteId }) {
  const toast = useToast()
  const { sites, chosen, setChosen } = useResolvedSite(siteId)
  const [assets, setAssets] = useState([])
  const [planDatasets, setPlanDatasets] = useState([])
  const [uploadBusy, setUploadBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)

  const [assetForm, setAssetForm] = useState({ kind: 'las', geomOrigin: 'AI_DERIVED', zRef: 'LOCAL_SITE', localZeroM: '0', epsg: '32643' })
  const [buildForm, setBuildForm] = useState({
    parcelCode: '',
    buildingCode: '',
    pointCloudId: '',
    dsmId: '',
    dtmId: '',
    thresholdM: '2.5',
    storeys: '',
    assumedStoreyHeightM: '3.0',
    planDatasetId: '',
  })

  const loadSources = useCallback(() => {
    listDatasets()
      .then((response) => {
        const rows = response.datasets || []
        setAssets(rows.filter((dataset) => ['las', 'dsm', 'dtm'].includes(dataset.kind)))
        setPlanDatasets(rows.filter((dataset) => !['las', 'dsm', 'dtm', 'derived-building'].includes(dataset.kind)))
      })
      .catch(() => {
        setAssets([])
        setPlanDatasets([])
      })
  }, [])
  useEffect(() => loadSources(), [loadSources])

  async function upload() {
    const file = fileRef.current?.files?.[0]
    if (!chosen) return toast.warning('Choose a site first.')
    if (!file) return toast.warning('Choose a LAS/LAZ or GeoTIFF file to upload.')
    setUploadBusy(true)
    try {
      const res = await uploadElevationFile({
        file,
        siteId: chosen,
        kind: assetForm.kind,
        geomOrigin: assetForm.geomOrigin,
        zRef: assetForm.zRef,
        localZeroM: assetForm.zRef === 'LOCAL_SITE' ? 0 : Number(assetForm.localZeroM || 0),
        epsg: assetForm.epsg ? Number(assetForm.epsg) : undefined,
      })
      toast.success(`${res.filename} registered as ${res.kind}.`, { title: res.reused ? 'Asset already registered' : 'Asset uploaded' })
      setAssets((prev) => [res, ...prev.filter((a) => a.id !== res.id)])
      if (fileRef.current) fileRef.current.value = ''
    } catch (err) {
      toast.error(err.message, { title: 'Upload failed' })
    } finally {
      setUploadBusy(false)
    }
  }

  async function submitBuilding() {
    if (!chosen) return toast.warning('Choose a site first.')
    if (!buildForm.parcelCode || !buildForm.buildingCode) return toast.warning('Parcel code and building code are required.')
    const usingCloud = Boolean(buildForm.pointCloudId)
    if (!usingCloud && !(buildForm.dsmId && buildForm.dtmId)) {
      return toast.warning('Provide a point cloud, or both a DSM and a DTM.')
    }
    setBusy(true)
    try {
      const payload = {
        site_id: chosen,
        parcel_code: buildForm.parcelCode,
        building_code: buildForm.buildingCode,
        threshold_m: Number(buildForm.thresholdM),
        assumed_storey_height_m: Number(buildForm.assumedStoreyHeightM),
        ...(buildForm.storeys ? { storeys: Number(buildForm.storeys) } : {}),
        ...(buildForm.planDatasetId ? { plan_dataset_id: buildForm.planDatasetId } : {}),
        ...(usingCloud
          ? { point_cloud_id: buildForm.pointCloudId }
          : { dsm_id: buildForm.dsmId, dtm_id: buildForm.dtmId }),
      }
      const res = await processBuilding(payload)
      setResult(res)
      toast.success(`Measured height ${res.metrics.height_m?.toFixed(2)} m via ${res.metrics.method}.`, { title: 'Building measured' })
    } catch (err) {
      toast.error(err.message, { title: 'Measurement failed' })
    } finally {
      setBusy(false)
    }
  }

  const siteAssets = assets.filter((asset) => asset.site_id === chosen)
  const sitePlans = planDatasets.filter((dataset) => dataset.site_id === chosen)
  const lasAssets = siteAssets.filter((a) => a.kind === 'las')
  const dsmAssets = siteAssets.filter((a) => a.kind === 'dsm')
  const dtmAssets = siteAssets.filter((a) => a.kind === 'dtm')

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Card className="space-y-3 p-5">
        <h2 className="text-sm font-semibold text-ink-primary">Upload elevation evidence</h2>
        <p className="text-xs text-ink-secondary">LAS/LAZ point clouds, or paired single-band GeoTIFF DSM + DTM rasters.</p>
        <SitePicker sites={sites} value={chosen} onChange={setChosen} />
        <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-hairline bg-black/[0.02] px-3 py-5 text-xs text-ink-muted transition hover:border-accent-blue/40">
          <FileUp size={16} />
          Choose a file
          <input ref={fileRef} type="file" className="hidden" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Kind">
            <select className={inputClass} value={assetForm.kind} onChange={(e) => setAssetForm({ ...assetForm, kind: e.target.value })}>
              <option value="las">las (point cloud)</option>
              <option value="dsm">dsm (surface)</option>
              <option value="dtm">dtm (terrain)</option>
            </select>
          </Field>
          <Field label="Geometry origin">
            <select
              className={inputClass}
              value={assetForm.geomOrigin}
              onChange={(e) => setAssetForm({ ...assetForm, geomOrigin: e.target.value })}
            >
              {['SURVEY', 'PLAN', 'AI_DERIVED', 'SYNTHETIC', 'MANUAL'].map((o) => (
                <option key={o}>{o}</option>
              ))}
            </select>
          </Field>
          <Field label="Vertical reference">
            <select className={inputClass} value={assetForm.zRef} onChange={(e) => setAssetForm({ ...assetForm, zRef: e.target.value })}>
              {['LOCAL_SITE', 'ORTHOMETRIC_EGM', 'ELLIPSOIDAL_WGS84'].map((z) => (
                <option key={z}>{z}</option>
              ))}
            </select>
          </Field>
          <Field label="Local zero (m)" hint="Offset if not LOCAL_SITE">
            <input
              className={`${inputClass} font-mono`}
              value={assetForm.localZeroM}
              onChange={(e) => setAssetForm({ ...assetForm, localZeroM: e.target.value })}
              disabled={assetForm.zRef === 'LOCAL_SITE'}
            />
          </Field>
        </div>
        <Button onClick={upload} loading={uploadBusy} icon={UploadCloud} className="w-full">
          Upload asset
        </Button>
        {siteAssets.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {siteAssets.map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-lg bg-black/[0.03] px-3 py-1.5 text-[11px]">
                <span className="font-mono text-ink-secondary">{a.filename}</span>
                <span className="text-ink-muted">{a.kind}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card className="space-y-3 p-5">
        <h2 className="text-sm font-semibold text-ink-primary">Measure a building</h2>
        <p className="text-xs text-ink-secondary">
          Elevation evidence measures the outer envelope. A plan supplies floor and apartment boundaries; without one, floor bands are proposals that require review.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Parcel local_code" required>
            <input
              className={`${inputClass} font-mono`}
              value={buildForm.parcelCode}
              onChange={(e) => setBuildForm({ ...buildForm, parcelCode: e.target.value })}
              placeholder="LOT"
            />
          </Field>
          <Field label="Building local_code" required>
            <input
              className={`${inputClass} font-mono`}
              value={buildForm.buildingCode}
              onChange={(e) => setBuildForm({ ...buildForm, buildingCode: e.target.value })}
              placeholder="B1"
            />
          </Field>
        </div>
        <Field label="Floor plan dataset" hint="Optional. Plan levels take precedence over generated bands.">
          <select
            className={inputClass}
            value={buildForm.planDatasetId}
            onChange={(e) => setBuildForm({ ...buildForm, planDatasetId: e.target.value })}
          >
            <option value="">No plan — propose floor bands</option>
            {sitePlans.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.filename} ({dataset.kind})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Point cloud" hint="Leave blank to use a DSM + DTM pair instead">
          <select
            className={inputClass}
            value={buildForm.pointCloudId}
            onChange={(e) => setBuildForm({ ...buildForm, pointCloudId: e.target.value })}
          >
            <option value="">None</option>
            {lasAssets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.filename}
              </option>
            ))}
          </select>
        </Field>
        {!buildForm.pointCloudId && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="DSM">
              <select className={inputClass} value={buildForm.dsmId} onChange={(e) => setBuildForm({ ...buildForm, dsmId: e.target.value })}>
                <option value="">Select…</option>
                {dsmAssets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.filename}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="DTM">
              <select className={inputClass} value={buildForm.dtmId} onChange={(e) => setBuildForm({ ...buildForm, dtmId: e.target.value })}>
                <option value="">Select…</option>
                {dtmAssets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.filename}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        )}
        {!buildForm.planDatasetId && <div className="grid grid-cols-2 gap-3">
          <Field label="Declared storeys" hint="Optional operator input">
            <input
              className={`${inputClass} font-mono`}
              type="number"
              min="1"
              max="200"
              step="1"
              value={buildForm.storeys}
              onChange={(e) => setBuildForm({ ...buildForm, storeys: e.target.value })}
              placeholder="Infer from height"
            />
          </Field>
          <Field label="Height threshold (m)">
            <input
              className={`${inputClass} font-mono`}
              value={buildForm.thresholdM}
              onChange={(e) => setBuildForm({ ...buildForm, thresholdM: e.target.value })}
            />
          </Field>
          <Field label="Assumed storey height (m)">
            <input
              className={`${inputClass} font-mono`}
              value={buildForm.assumedStoreyHeightM}
              onChange={(e) => setBuildForm({ ...buildForm, assumedStoreyHeightM: e.target.value })}
            />
          </Field>
        </div>}
        {buildForm.planDatasetId && (
          <Field label="Height threshold (m)">
            <input
              className={`${inputClass} font-mono`}
              value={buildForm.thresholdM}
              onChange={(e) => setBuildForm({ ...buildForm, thresholdM: e.target.value })}
            />
          </Field>
        )}
        <Button onClick={submitBuilding} loading={busy} icon={Layers} className="w-full">
          Measure &amp; propose
        </Button>

        {result && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-lg border border-hairline bg-black/[0.03] p-3 text-xs">
            <p className="font-tabular text-ink-primary">
              Height <strong>{result.metrics.height_m?.toFixed(2)} m</strong> · method <span className="font-mono">{result.metrics.method}</span>
            </p>
            {result.metrics.floor_segmentation && (
              <div className="mt-2 space-y-1 text-ink-secondary">
                <p>
                  Floors: <strong>{result.metrics.floor_segmentation.floor_count}</strong> ·{' '}
                  <span className="font-mono">{result.metrics.floor_segmentation.method}</span>
                </p>
                <p>Evidence: {result.metrics.floor_segmentation.evidence.replaceAll('_', ' ').toLowerCase()}</p>
                {result.metrics.floor_segmentation.requires_review && (
                  <p className="font-medium text-status-warning">Review required before issuance</p>
                )}
                {result.metrics.floor_segmentation.apartment_boundaries_supplied && (
                  <p>Apartments supplied by plan: {result.metrics.floor_segmentation.apartment_boundary_count}</p>
                )}
              </div>
            )}
            {result.metrics.assumptions?.length > 0 && (
              <ul className="mt-2 list-disc space-y-1 pl-4 text-ink-muted">
                {result.metrics.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
            )}
          </motion.div>
        )}
      </Card>
    </div>
  )
}
