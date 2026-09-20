import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { ShieldCheck, ShieldAlert, ShieldX, ListChecks, Play } from 'lucide-react'
import { Card, StatTile, Button, EmptyState, PageSpinner, Badge } from '../components/ui/primitives.jsx'
import { getValidationLatest, runValidation } from '../lib/api.js'
import { useToast } from '../lib/ToastContext.jsx'
import { useLiveRefresh } from '../lib/LiveContext.jsx'
import { truncateId } from '../lib/format.js'

const STATUS = {
  good: '#0ca30c',
  warning: '#fab219',
  critical: '#d03b3b',
}

export default function ValidationPage() {
  const toast = useToast()
  const [results, setResults] = useState(null)
  const [busy, setBusy] = useState(false)
  const [ruleFilter, setRuleFilter] = useState(null)

  const load = useCallback(() => {
    getValidationLatest()
      .then((r) => setResults(r.results))
      .catch(() => setResults([]))
  }, [])

  useEffect(() => load(), [load])

  useLiveRefresh(['demo.seeded', 'demo.degraded', 'demo.overlap_fixed', 'validation.run'], load)

  async function handleRun() {
    setBusy(true)
    try {
      const res = await runValidation()
      toast.info(`${res.finding_count} findings, ${res.error_count} blocking errors.`, { title: 'Validation run complete' })
      load()
    } catch (e) {
      toast.error(e.message)
    } finally {
      setBusy(false)
    }
  }

  const byRule = useMemo(() => {
    const map = new Map()
    for (const r of results || []) {
      const entry = map.get(r.rule_code) || { rule_code: r.rule_code, passed: 0, failed: 0, severity: r.severity }
      r.passed ? entry.passed++ : entry.failed++
      if (!r.passed) entry.severity = r.severity
      map.set(r.rule_code, entry)
    }
    return [...map.values()].sort((a, b) => b.failed - a.failed || a.rule_code.localeCompare(b.rule_code))
  }, [results])

  const totals = useMemo(() => {
    const failed = (results || []).filter((r) => !r.passed)
    return {
      total: results?.length || 0,
      passed: (results || []).filter((r) => r.passed).length,
      errors: failed.filter((r) => r.severity === 'ERROR').length,
      warnings: failed.filter((r) => r.severity === 'WARN').length,
    }
  }, [results])

  const findings = useMemo(() => {
    const failedOnly = (results || []).filter((r) => !r.passed)
    return ruleFilter ? failedOnly.filter((r) => r.rule_code === ruleFilter) : failedOnly
  }, [results, ruleFilter])

  if (results === null) return <PageSpinner label="Loading validation results…" />

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-xs text-ink-secondary">
          Deterministic geometry rules — overlap, containment, Z-continuity — are the only thing that decides VALID.
        </p>
        <Button onClick={handleRun} loading={busy} icon={Play}>
          Run validation
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Total findings" value={totals.total} icon={ListChecks} tone="blue" />
        <StatTile label="Passed" value={totals.passed} icon={ShieldCheck} tone="aqua" />
        <StatTile label="Blocking errors" value={totals.errors} icon={ShieldX} tone={totals.errors ? 'red' : 'aqua'} />
        <StatTile label="Warnings" value={totals.warnings} icon={ShieldAlert} tone={totals.warnings ? 'yellow' : 'aqua'} />
      </div>

      {byRule.length === 0 ? (
        <EmptyState icon={ShieldCheck} title="No validation runs yet" description="Run validation to check topology, overlap and containment rules." />
      ) : (
        <Card className="p-5">
          <h2 className="mb-4 text-sm font-semibold text-ink-primary">Findings by rule</h2>
          <div className="space-y-3">
            {byRule.map((rule, i) => {
              const total = rule.passed + rule.failed
              const passPct = total ? (rule.passed / total) * 100 : 0
              const barColor = rule.failed === 0 ? STATUS.good : rule.severity === 'ERROR' ? STATUS.critical : STATUS.warning
              return (
                <motion.button
                  key={rule.rule_code}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                  onClick={() => setRuleFilter(ruleFilter === rule.rule_code ? null : rule.rule_code)}
                  className={`w-full rounded-lg px-2 py-1.5 text-left transition ${ruleFilter === rule.rule_code ? 'bg-black/[0.05]' : 'hover:bg-black/[0.03]'}`}
                >
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-mono font-medium text-ink-primary">{rule.rule_code}</span>
                    <span className="font-tabular text-ink-secondary">
                      {rule.passed}/{total} passed
                      {rule.failed > 0 && <span className="ml-1.5 text-ink-muted">· {rule.failed} failed</span>}
                    </span>
                  </div>
                  <div className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-black/[0.04]">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${passPct}%`, background: STATUS.good, opacity: 0.85 }}
                    />
                    {rule.failed > 0 && (
                      <div
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${100 - passPct}%`, background: barColor }}
                      />
                    )}
                  </div>
                </motion.button>
              )
            })}
          </div>
        </Card>
      )}

      {findings.length > 0 && (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
            <h2 className="text-sm font-semibold text-ink-primary">
              Failing findings {ruleFilter && <span className="text-ink-muted">· {ruleFilter}</span>}
            </h2>
            {ruleFilter && (
              <button onClick={() => setRuleFilter(null)} className="text-xs text-accent-blue hover:underline">
                clear filter
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-surface-panel">
                <tr className="border-b border-hairline text-[10px] uppercase tracking-wide text-ink-muted">
                  <th className="px-4 py-2 font-medium">Rule</th>
                  <th className="px-4 py-2 font-medium">Severity</th>
                  <th className="px-4 py-2 font-medium">Unit</th>
                  <th className="px-4 py-2 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((f, i) => (
                  <tr key={i} className="border-b border-hairline/60">
                    <td className="px-4 py-2 font-mono text-ink-primary">{f.rule_code}</td>
                    <td className="px-4 py-2">
                      <Badge color={f.severity === 'ERROR' ? STATUS.critical : STATUS.warning}>{f.severity}</Badge>
                    </td>
                    <td className="px-4 py-2 font-mono text-ink-muted">{truncateId(f.spatial_unit_id, 8)}</td>
                    <td className="max-w-md truncate px-4 py-2 text-ink-secondary">{JSON.stringify(f.detail)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
