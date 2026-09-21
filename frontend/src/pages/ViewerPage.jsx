import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Box,
  RotateCw,
  Locate,
  Layers3,
  Eye,
  EyeOff,
  ShieldCheck,
  ClipboardCheck,
  X,
  PlayCircle,
  Maximize2,
} from 'lucide-react'
import ModelViewer from '../components/viewer/ModelViewer.jsx'
import RecordCard from '../components/record/RecordCard.jsx'
import { Button, EmptyState, PageSpinner, Badge } from '../components/ui/primitives.jsx'
import { listUnits, seedDemo, issueUnit } from '../lib/api.js'
import { classMeta, statusMeta, formatMeters, formatVolume, formatPercent } from '../lib/format.js'
import { useToast } from '../lib/ToastContext.jsx'
import clsx from '../lib/clsx.js'

const TOGGLE_CLASSES = ['PARCEL', 'BUILDING', 'FLOOR', 'UNIT', 'COMMON', 'PARKING', 'BALCONY', 'UTILITY']

export default function ViewerPage({ siteId, navigateTo }) {
  const toast = useToast()
  const [units, setUnits] = useState(null)
  const [selected, setSelected] = useState(null)
  const [hovered, setHovered] = useState(null)
  const [pointer, setPointer] = useState({ x: 0, y: 0 })
  const [explode, setExplode] = useState(0)
  const [autoRotate, setAutoRotate] = useState(true)
  const [hiddenClasses, setHiddenClasses] = useState(() => new Set())
  const [recordOpen, setRecordOpen] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const [issuing, setIssuing] = useState(false)
  const controlsRef = useRef(null)

  const load = useCallback(() => {
    listUnits(siteId)
      .then((r) => setUnits(r.units))
      .catch(() => setUnits([]))
  }, [siteId])

  useEffect(() => {
    setUnits(null)
    load()
  }, [load])

  async function handleSeed() {
    setSeeding(true)
    try {
      await seedDemo()
      toast.success('Demo scene ready — explore it below.', { title: 'Seeded' })
      load()
    } catch (e) {
      toast.error(e.message)
    } finally {
      setSeeding(false)
    }
  }

  async function handleIssue() {
    if (!selected) return
    setIssuing(true)
    try {
      const res = await issueUnit(selected.local_code, siteId)
      toast.success(res.display_id, { title: 'Proposed 3D ULPIN issued' })
      load()
    } catch (e) {
      toast.error(e.message, { title: 'Could not issue' })
    } finally {
      setIssuing(false)
    }
  }

  function toggleClass(cls) {
    setHiddenClasses((prev) => {
      const next = new Set(prev)
      next.has(cls) ? next.delete(cls) : next.add(cls)
      return next
    })
  }

  function handleHover(unit, e) {
    setHovered(unit)
    if (unit && e) setPointer({ x: e.clientX, y: e.clientY })
  }

  if (units === null) return <PageSpinner label="Loading the 3D scene…" />

  const solidCount = units.filter((u) => ['FLOOR', 'UNIT', 'COMMON', 'PARKING', 'BALCONY', 'UTILITY', 'AIR', 'SUBSURFACE'].includes(u.su_class)).length

  if (solidCount === 0) {
    return (
      <EmptyState
        icon={Box}
        title="No validated volumes to render yet"
        description="Seed the demo scene, or import and process a dataset, to see the live 3D cadastral model."
        action={
          <Button onClick={handleSeed} loading={seeding} icon={PlayCircle}>
            Seed the demo scene
          </Button>
        }
      />
    )
  }

  const cls = selected ? classMeta(selected.su_class) : null
  const status = selected ? statusMeta(selected.topology_status) : null

  return (
    <div className="relative">
      <div className="relative h-[70vh] min-h-[520px] overflow-hidden rounded-2xl border border-hairline shadow-panel">
        <ModelViewer
          units={units}
          selectedId={selected?.uuid}
          onSelect={setSelected}
          onHover={handleHover}
          explode={explode}
          autoRotate={autoRotate}
          hiddenClasses={hiddenClasses}
          controlsRef={controlsRef}
          onPointerMissed={() => setSelected(null)}
        />

        {/* Legend & class toggles */}
        <div className="glass pointer-events-auto absolute left-3 top-3 max-w-[13rem] rounded-xl border border-hairline p-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink-secondary">
            <Layers3 size={12} /> Layers
          </p>
          <div className="space-y-1">
            {TOGGLE_CLASSES.map((c) => {
              const meta = classMeta(c)
              const hidden = hiddenClasses.has(c)
              return (
                <button
                  key={c}
                  onClick={() => toggleClass(c)}
                  className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[11px] text-ink-secondary transition hover:bg-black/[0.06]"
                >
                  <span className="h-2 w-2 rounded-full" style={{ background: meta.color, opacity: hidden ? 0.25 : 1 }} />
                  <span className={clsx('flex-1', hidden && 'text-ink-muted line-through')}>{meta.label}</span>
                  {hidden ? <EyeOff size={11} className="text-ink-muted" /> : <Eye size={11} className="text-ink-muted" />}
                </button>
              )
            })}
          </div>
        </div>

        {/* View controls */}
        <div className="pointer-events-auto absolute right-3 top-3 flex gap-2">
          <IconToggle active={autoRotate} onClick={() => setAutoRotate((v) => !v)} label="Auto-rotate">
            <RotateCw size={14} />
          </IconToggle>
          <IconToggle onClick={() => controlsRef.current?.reset()} label="Reset view">
            <Locate size={14} />
          </IconToggle>
        </div>

        {/* Explode slider */}
        <div className="glass pointer-events-auto absolute bottom-3 left-1/2 flex w-[min(90%,22rem)] -translate-x-1/2 items-center gap-3 rounded-full border border-hairline px-4 py-2.5">
          <Maximize2 size={13} className="shrink-0 text-ink-muted" />
          <input
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={explode}
            onChange={(e) => setExplode(Number(e.target.value))}
            className="h-1 w-full cursor-pointer appearance-none rounded-full bg-hairline accent-accent-blue"
          />
          <span className="font-tabular w-10 shrink-0 text-right text-[11px] text-ink-secondary">{Math.round(explode * 100)}%</span>
        </div>

        {/* Hover tooltip */}
        <AnimatePresence>
          {hovered && !selected && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.12 }}
              className="glass pointer-events-none fixed z-50 rounded-lg border border-hairline px-2.5 py-1.5 text-xs"
              style={{ left: pointer.x + 14, top: pointer.y + 14 }}
            >
              <p className="font-mono font-semibold text-ink-primary">{hovered.local_code}</p>
              <p className="text-[10px] text-ink-muted">{classMeta(hovered.su_class).label} · {statusMeta(hovered.topology_status).label}</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Selection side panel */}
        <AnimatePresence>
          {selected && (
            <motion.div
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 24 }}
              transition={{ type: 'spring', stiffness: 360, damping: 34 }}
              className="glass pointer-events-auto absolute bottom-3 right-3 top-3 w-[19rem] overflow-y-auto rounded-xl border border-hairline p-4"
            >
              <div className="mb-3 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-mono text-sm font-semibold text-ink-primary">{selected.local_code}</p>
                  <p className="truncate text-[11px] text-ink-muted">{selected.display_id}</p>
                </div>
                <button onClick={() => setSelected(null)} className="shrink-0 rounded-md p-1 text-ink-muted hover:bg-black/5">
                  <X size={14} />
                </button>
              </div>

              <div className="mb-4 flex flex-wrap gap-1.5">
                <Badge color={cls.color}>{cls.label}</Badge>
                <Badge color={status.color} pulse={selected.topology_status === 'DEGRADED'}>
                  {status.label}
                </Badge>
              </div>

              <dl className="space-y-2.5 text-xs">
                <Row label="Height" value={`${formatMeters(selected.zmin, 1)} → ${formatMeters(selected.zmax, 1)}`} />
                <Row label="Volume" value={formatVolume(selected.volume_m3)} />
                <Row label="Origin" value={selected.geom_origin} />
                <Row label="Confidence" value={selected.confidence !== null ? formatPercent(selected.confidence) : '—'} />
              </dl>

              <div className="mt-4 space-y-2">
                <Button className="w-full" variant="ghost" onClick={() => setRecordOpen(true)}>
                  Open full record
                </Button>
                {selected.topology_status === 'DEGRADED' && (
                  <Button
                    className="w-full"
                    variant="ghost"
                    icon={ClipboardCheck}
                    onClick={() => navigateTo('review', selected.local_code)}
                  >
                    Review this unit
                  </Button>
                )}
                {selected.topology_status === 'VALID' && selected.display_id?.startsWith('UNISSUED') && (
                  <Button className="w-full" variant="success" icon={ShieldCheck} loading={issuing} onClick={handleIssue}>
                    Issue proposed 3D ULPIN
                  </Button>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <p className="mt-3 text-center text-[11px] text-ink-muted">
        Built live from validated spatial units — drag to orbit, scroll to zoom, click a volume to inspect it.
      </p>

      <RecordCard localCode={selected?.local_code} siteId={siteId} open={recordOpen} onClose={() => setRecordOpen(false)} />
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-hairline/60 pb-2">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="font-tabular font-medium text-ink-primary">{value}</dd>
    </div>
  )
}

function IconToggle({ active, onClick, children, label }) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={clsx(
        'glass flex h-8 w-8 items-center justify-center rounded-full border border-hairline transition',
        active ? 'text-accent-blue' : 'text-ink-secondary hover:text-ink-primary',
      )}
    >
      {children}
    </button>
  )
}
