import React, { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Boxes, MapPinned, Scale, ShieldCheck, Box, ShieldAlert, ArrowRight, PlayCircle } from 'lucide-react'
import { Card, StatTile, Meter, Button, PageSpinner } from '../components/ui/primitives.jsx'
import { useToast } from '../lib/ToastContext.jsx'
import { getHealth, listSites, listUnits, listRRR, getValidationLatest, seedDemo, runValidation } from '../lib/api.js'
import { formatNumber } from '../lib/format.js'
import { useLive, useLiveRefresh } from '../lib/LiveContext.jsx'
import clsx from '../lib/clsx.js'

export default function OverviewPage({ siteId, navigateTo }) {
  const toast = useToast()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [health, sites, units, rrr, validation] = await Promise.allSettled([
        getHealth(),
        listSites(),
        listUnits(siteId),
        listRRR(siteId),
        getValidationLatest(),
      ])
      setData({
        health: health.status === 'fulfilled' ? health.value : null,
        sites: sites.status === 'fulfilled' ? sites.value.sites : [],
        units: units.status === 'fulfilled' ? units.value.units : [],
        rrr: rrr.status === 'fulfilled' ? rrr.value.rrr : [],
        validation: validation.status === 'fulfilled' ? validation.value.results : [],
      })
    } finally {
      setLoading(false)
    }
  }, [siteId])

  useEffect(() => {
    load()
  }, [load])

  // The dashboard is the most-watched screen in a demo, so it's the one
  // that should visibly come alive: whenever the stream reports something
  // that changes these numbers, quietly refetch (no spinner — `load` only
  // shows one while `data` is still empty) and let the stat tiles count up.
  useLiveRefresh(
    ['demo.seeded', 'demo.degraded', 'demo.overlap_fixed', 'site.created', 'dataset.processed', 'rrr.recorded', 'unit.reviewed', 'unit.issued', 'unit.withdrawn', 'validation.run'],
    load,
  )

  async function handleSeed() {
    setBusy(true)
    try {
      const res = await seedDemo()
      toast.success(`Seeded ${res.spatial_units} spatial units across the demo site.`, { title: 'Demo scene ready' })
      await load()
    } catch (e) {
      toast.error(e.message, { title: 'Could not seed demo' })
    } finally {
      setBusy(false)
    }
  }

  async function handleValidate() {
    setBusy(true)
    try {
      const res = await runValidation()
      toast.info(`${res.finding_count} findings, ${res.error_count} blocking errors.`, { title: 'Validation run complete' })
      await load()
    } catch (e) {
      toast.error(e.message, { title: 'Validation failed' })
    } finally {
      setBusy(false)
    }
  }

  if (loading && !data) return <PageSpinner label="Loading workspace…" />

  const units = data?.units || []
  const validUnits = units.filter((u) => u.topology_status === 'VALID').length
  const degradedUnits = units.filter((u) => u.topology_status === 'DEGRADED').length
  const errorFindings = (data?.validation || []).filter((f) => !f.passed && f.severity === 'ERROR').length

  return (
    <div className="space-y-8">
      <Hero onSeed={handleSeed} onViewModel={() => navigateTo('viewer')} busy={busy} hasData={units.length > 0} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Spatial units" value={formatNumber(units.length)} icon={Boxes} tone="blue" delay={0} hint="Active, this scope" />
        <StatTile label="Sites" value={formatNumber(data?.sites?.length || 0)} icon={MapPinned} tone="aqua" delay={0.05} hint="Registered parcels of work" />
        <StatTile label="Recorded RRR" value={formatNumber(data?.rrr?.length || 0)} icon={Scale} tone="violet" delay={0.1} hint="Rights, restrictions, responsibilities" />
        <StatTile
          label="Blocking errors"
          value={formatNumber(errorFindings)}
          icon={ShieldAlert}
          tone={errorFindings ? 'red' : 'aqua'}
          delay={0.15}
          hint="From the latest validation run"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-primary">Topology health</h2>
            <Button variant="ghost" onClick={handleValidate} loading={busy} icon={ShieldCheck}>
              Run validation
            </Button>
          </div>
          <div className="space-y-4">
            <Meter label="Valid topology" value={validUnits} total={units.length || 1} tone="good" hint={`${validUnits} / ${units.length}`} />
            <Meter
              label="Awaiting review (degraded)"
              value={degradedUnits}
              total={units.length || 1}
              tone="warning"
              hint={`${degradedUnits} / ${units.length}`}
            />
          </div>
          <p className="mt-4 text-xs leading-relaxed text-ink-muted">
            Deterministic geometry validation is the only thing that can mark a spatial unit VALID — a human review
            approval never sets topology directly. See the Validation tab for the full rule breakdown.
          </p>
        </Card>

        <Card className="flex flex-col p-5">
          <h2 className="text-sm font-semibold text-ink-primary">How this all fits together</h2>
          <p className="mb-3 mt-1 text-xs text-ink-secondary">Five steps take a flat parcel to a reviewed, volumetric record:</p>
          <ol className="flex-1 space-y-3 text-xs text-ink-secondary">
            <Step n={1} text="Register a site and import surveyed, planned, or AI-derived geometry." />
            <Step n={2} text="Construct the parcel → building → floor → unit prism hierarchy." />
            <Step n={3} text="Deterministic rules validate overlap, containment and Z-continuity." />
            <Step n={4} text="Degraded geometry needs an evidenced human review before it can be released." />
            <Step n={5} text="Only VALID, reviewed units can be issued a proposed 3D ULPIN display id." />
          </ol>
          <Button variant="ghost" className="mt-4 justify-between" onClick={() => navigateTo('import')}>
            Start an import <ArrowRight size={14} />
          </Button>
        </Card>

        <LiveActivityCard />
      </div>
    </div>
  )
}

// A live-updating feed of what's actually happening on the backend, pulled
// from the same SSE stream that drives the header's "Live" pill — seed the
// demo in another tab and this updates here with nobody touching refresh.
function LiveActivityCard() {
  const { status, events } = useLive()
  const recent = events.slice(0, 6)

  return (
    <Card className="flex flex-col p-5 lg:col-span-3">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink-primary">Live activity</h2>
        <span className={clsx('flex items-center gap-1.5 text-[11px]', status === 'live' ? 'text-status-good' : 'text-ink-muted')}>
          <span className={clsx('h-1.5 w-1.5 rounded-full', status === 'live' ? 'bg-status-good animate-pulse-glow' : 'bg-ink-muted')} />
          {status === 'live' ? 'Streaming' : 'Reconnecting…'}
        </span>
      </div>
      {recent.length === 0 ? (
        <p className="text-xs text-ink-secondary">
          Nothing yet in this session — seed the demo, run an import, or record a review and it'll show up here the
          instant it happens, not on the next refresh.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-x-6 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
          <AnimatePresence initial={false}>
            {recent.map((e) => (
              <motion.li
                key={e.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex gap-2 text-ink-secondary"
              >
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-blue" />
                <span>{e.text}</span>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </Card>
  )
}

function Step({ n, text }) {
  return (
    <li className="flex gap-2.5">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-blue/15 text-[10px] font-semibold text-accent-blue">
        {n}
      </span>
      <span className="leading-relaxed">{text}</span>
    </li>
  )
}

function Hero({ onSeed, onViewModel, busy, hasData }) {
  return (
    <Card className="relative overflow-hidden p-6 sm:p-8">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-40 [mask-image:radial-gradient(ellipse_at_top_left,black,transparent_70%)]" />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="max-w-xl">
          <motion.h1
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="font-serif text-[28px] font-medium leading-[1.15] tracking-tight text-ink-primary sm:text-[34px]"
          >
            Property records that finally have a{' '}
            <em className="text-accent-blue font-semibold not-italic">height</em>.
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="mt-3 text-sm leading-relaxed text-ink-secondary"
          >
            Stratum extends the flat land parcel into a validated stack of legal volumes — buildings, floors,
            units, common areas, and utility corridors — each with its own provenance, review trail and proposed
            3D identifier.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="mt-5 flex flex-wrap gap-3"
          >
            <Button onClick={onSeed} loading={busy} icon={PlayCircle}>
              Seed the demo scene
            </Button>
            <Button variant="ghost" onClick={onViewModel} icon={Box}>
              {hasData ? 'Open the 3D model' : 'Preview the 3D viewer'}
            </Button>
          </motion.div>
        </div>
        <motion.div
          initial={{ opacity: 0, scale: 0.9, rotate: -6 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }}
          transition={{ delay: 0.15, duration: 0.5, ease: 'easeOut' }}
          className="relative hidden h-40 w-40 shrink-0 items-center justify-center lg:flex"
        >
          <StackGlyph />
        </motion.div>
      </div>
    </Card>
  )
}

function StackGlyph() {
  const layers = [
    { y: 0, w: 96, c: '#2a78d6' },
    { y: 22, w: 88, c: '#1baf7a' },
    { y: 44, w: 80, c: '#4a3aa7' },
    { y: 66, w: 72, c: '#eda100' },
  ]
  return (
    <svg viewBox="0 0 120 120" className="relative h-32 w-32">
      {layers.map((l, i) => (
        <motion.g
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 + i * 0.08, duration: 0.4 }}
        >
          <rect x={(120 - l.w) / 2} y={90 - l.y} width={l.w} height={16} rx={3} fill={l.c} opacity={0.85} />
        </motion.g>
      ))}
    </svg>
  )
}
