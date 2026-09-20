import React, { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { FileJson, UploadCloud, Layers, Play, CheckCircle2, FileUp, Satellite } from 'lucide-react'
import { Card, Button, Field, inputClass, EmptyState } from '../components/ui/primitives.jsx'
import { useToast } from '../lib/ToastContext.jsx'
import {
  listDatasets,
  createDataset,
  processDataset,
  uploadElevationFile,
  processBuilding,
  listSites,
} from '../lib/api.js'
import clsx from '../lib/clsx.js'

const TABS = [
  { key: 'geojson', label: 'Property GeoJSON', icon: FileJson },
  { key: 'elevation', label: 'Elevation → building', icon: Satellite },
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
      {tab === 'geojson' ? <GeoJsonImport siteId={siteId} /> : <ElevationImport siteId={siteId} />}
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

// --- Elevation → building pipeline -------------------------------------

function ElevationImport({ siteId }) {
  const toast = useToast()
  const { sites, chosen, setChosen } = useResolvedSite(siteId)
  const [assets, setAssets] = useState([])
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
    assumedStoreyHeightM: '3.0',
  })

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

  const lasAssets = assets.filter((a) => a.kind === 'las')
  const dsmAssets = assets.filter((a) => a.kind === 'dsm')
  const dtmAssets = assets.filter((a) => a.kind === 'dtm')

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
        {assets.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {assets.map((a) => (
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
          Classical nDSM extraction — not a trained model. Produces a review-required proposal, never issued automatically.
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
        <div className="grid grid-cols-2 gap-3">
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
        </div>
        <Button onClick={submitBuilding} loading={busy} icon={Layers} className="w-full">
          Measure &amp; propose
        </Button>

        {result && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-lg border border-hairline bg-black/[0.03] p-3 text-xs">
            <p className="font-tabular text-ink-primary">
              Height <strong>{result.metrics.height_m?.toFixed(2)} m</strong> · method <span className="font-mono">{result.metrics.method}</span>
            </p>
            {result.metrics.floor_count && <p className="mt-1 text-ink-secondary">Proposed floors: {result.metrics.floor_count}</p>}
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
