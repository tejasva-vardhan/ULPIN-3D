import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Search, Boxes, RotateCw, ShieldCheck } from 'lucide-react'
import { Card, Badge, Button, EmptyState, PageSpinner, inputClass } from '../components/ui/primitives.jsx'
import RecordCard from '../components/record/RecordCard.jsx'
import { listUnits, issueUnit } from '../lib/api.js'
import { classMeta, statusMeta, formatMeters, formatVolume, formatPercent } from '../lib/format.js'
import { useToast } from '../lib/ToastContext.jsx'
import { useLiveRefresh } from '../lib/LiveContext.jsx'
import clsx from '../lib/clsx.js'

const STATUS_FILTERS = ['ALL', 'VALID', 'PENDING', 'DEGRADED', 'INVALID']

export default function UnitsPage({ siteId, focusCode, clearFocusCode }) {
  const toast = useToast()
  const [units, setUnits] = useState(null)
  const [search, setSearch] = useState('')
  const [classFilter, setClassFilter] = useState(null)
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [selected, setSelected] = useState(focusCode || null)
  const [issuing, setIssuing] = useState(null)

  const load = useCallback(() => {
    listUnits(siteId)
      .then((r) => setUnits(r.units))
      .catch(() => setUnits([]))
  }, [siteId])

  useEffect(() => load(), [load])
  useEffect(() => {
    if (focusCode) setSelected(focusCode)
  }, [focusCode])

  useLiveRefresh(
    ['demo.seeded', 'demo.degraded', 'demo.overlap_fixed', 'dataset.processed', 'unit.reviewed', 'unit.issued', 'unit.withdrawn'],
    load,
  )

  const classes = useMemo(() => [...new Set((units || []).map((u) => u.su_class))], [units])

  const filtered = useMemo(() => {
    return (units || []).filter((u) => {
      if (classFilter && u.su_class !== classFilter) return false
      if (statusFilter !== 'ALL' && u.topology_status !== statusFilter) return false
      if (search && !u.local_code.toLowerCase().includes(search.toLowerCase())) return false
      return true
    })
  }, [units, classFilter, statusFilter, search])

  async function handleIssue(code) {
    setIssuing(code)
    try {
      const res = await issueUnit(code, siteId)
      toast.success(res.display_id, { title: 'Proposed 3D ULPIN issued' })
      load()
    } catch (err) {
      toast.error(err.message, { title: 'Could not issue' })
    } finally {
      setIssuing(null)
    }
  }

  if (units === null) return <PageSpinner label="Loading spatial units…" />

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input
            className={`${inputClass} w-56 pl-8`}
            placeholder="Search local_code…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <FilterChip active={!classFilter} onClick={() => setClassFilter(null)}>
          All classes
        </FilterChip>
        {classes.map((c) => (
          <FilterChip key={c} active={classFilter === c} onClick={() => setClassFilter(c)} color={classMeta(c).color}>
            {classMeta(c).label}
          </FilterChip>
        ))}
        <span className="mx-1 h-4 w-px bg-hairline" />
        {STATUS_FILTERS.map((s) => (
          <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)} color={s !== 'ALL' ? statusMeta(s).color : undefined}>
            {s === 'ALL' ? 'All statuses' : statusMeta(s).label}
          </FilterChip>
        ))}
        <Button variant="ghost" className="ml-auto" icon={RotateCw} onClick={load}>
          Refresh
        </Button>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title={units.length === 0 ? 'No spatial units yet' : 'No units match these filters'}
          description={units.length === 0 ? 'Seed the demo scene or import a dataset to populate this table.' : 'Try widening your filters.'}
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-hairline text-[10px] uppercase tracking-wide text-ink-muted">
                  <th className="px-4 py-2.5 font-medium">Local code</th>
                  <th className="px-4 py-2.5 font-medium">Class</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Height</th>
                  <th className="px-4 py-2.5 font-medium">Volume</th>
                  <th className="px-4 py-2.5 font-medium">Origin</th>
                  <th className="px-4 py-2.5 font-medium">Confidence</th>
                  <th className="px-4 py-2.5 font-medium" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((u, i) => {
                  const cls = classMeta(u.su_class)
                  const status = statusMeta(u.topology_status)
                  return (
                    <motion.tr
                      key={u.uuid}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: Math.min(i * 0.015, 0.3) }}
                      className="cursor-pointer border-b border-hairline/60 transition hover:bg-black/[0.03]"
                      onClick={() => setSelected(u.local_code)}
                    >
                      <td className="px-4 py-2.5 font-mono font-medium text-ink-primary">{u.local_code}</td>
                      <td className="px-4 py-2.5">
                        <Badge color={cls.color}>{cls.label}</Badge>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge color={status.color} pulse={u.topology_status === 'DEGRADED'}>
                          {status.label}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 font-tabular text-ink-secondary">
                        {formatMeters(u.zmin, 1)} – {formatMeters(u.zmax, 1)}
                      </td>
                      <td className="px-4 py-2.5 font-tabular text-ink-secondary">{formatVolume(u.volume_m3)}</td>
                      <td className="px-4 py-2.5 text-ink-muted">{u.geom_origin}</td>
                      <td className="px-4 py-2.5 font-tabular text-ink-secondary">
                        {u.confidence !== null && u.confidence !== undefined ? formatPercent(u.confidence) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        {u.topology_status === 'VALID' && u.display_id?.startsWith('UNISSUED') && (
                          <Button
                            variant="success"
                            loading={issuing === u.local_code}
                            icon={ShieldCheck}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleIssue(u.local_code)
                            }}
                          >
                            Issue
                          </Button>
                        )}
                      </td>
                    </motion.tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <RecordCard
        localCode={selected}
        siteId={siteId}
        open={Boolean(selected)}
        onClose={() => {
          setSelected(null)
          clearFocusCode?.()
        }}
      />
    </div>
  )
}

function FilterChip({ active, onClick, children, color }) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition',
        active ? 'border-accent-blue/40 bg-accent-blue/15 text-accent-blue' : 'border-hairline text-ink-secondary hover:text-ink-primary',
      )}
    >
      {color && <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />}
      {children}
    </button>
  )
}
