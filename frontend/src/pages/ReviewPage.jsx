import React, { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { ClipboardCheck, ClipboardX, History, AlertTriangle } from 'lucide-react'
import { Card, Button, Field, inputClass, EmptyState, PageSpinner, Badge } from '../components/ui/primitives.jsx'
import { useToast } from '../lib/ToastContext.jsx'
import { listUnits, postReview, getReviewHistory } from '../lib/api.js'
import { useLiveRefresh } from '../lib/LiveContext.jsx'
import { classMeta, formatDate } from '../lib/format.js'

export default function ReviewPage({ siteId, focusCode, clearFocusCode }) {
  const toast = useToast()
  const [units, setUnits] = useState(null)
  const [form, setForm] = useState({ local_code: '', reviewer_label: '', reason: '', evidence_ref: '', release: false })
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState(null)

  const load = useCallback(() => {
    listUnits(siteId)
      .then((r) => setUnits(r.units.filter((u) => u.topology_status === 'DEGRADED')))
      .catch(() => setUnits([]))
  }, [siteId])

  useEffect(() => load(), [load])
  useLiveRefresh(['demo.seeded', 'demo.degraded', 'demo.overlap_fixed', 'unit.reviewed', 'dataset.processed'], load)
  useEffect(() => {
    if (focusCode) {
      setForm((f) => ({ ...f, local_code: focusCode }))
      loadHistory(focusCode)
      clearFocusCode?.()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusCode])

  function loadHistory(code) {
    if (!code) return setHistory(null)
    getReviewHistory(code, siteId)
      .then((r) => setHistory(r.reviews))
      .catch(() => setHistory([]))
  }

  async function submit(decision) {
    if (!form.local_code) return toast.warning('Enter a local_code to review.')
    if (!form.reviewer_label.trim() || !form.reason.trim()) return toast.warning('Reviewer label and reason are required.')
    if (form.release && (decision !== 'APPROVED' || !form.evidence_ref.trim())) {
      return toast.warning('Releasing the block needs decision=APPROVED and an evidence_ref.')
    }
    setBusy(true)
    try {
      const res = await postReview(
        form.local_code,
        {
          decision,
          reviewer_label: form.reviewer_label,
          reason: form.reason,
          evidence_ref: form.evidence_ref || undefined,
          release_review_block: form.release,
        },
        siteId,
      )
      toast.success(`${res.local_code} is now ${res.topology_status}.`, { title: `Review ${decision.toLowerCase()}` })
      loadHistory(form.local_code)
      load()
    } catch (err) {
      toast.error(err.message, { title: 'Review failed' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
      <div className="lg:col-span-2">
        <h2 className="mb-3 text-sm font-semibold text-ink-primary">Awaiting review</h2>
        {units === null ? (
          <PageSpinner label="Loading…" />
        ) : units.length === 0 ? (
          <EmptyState icon={ClipboardCheck} title="Nothing DEGRADED right now" description="Units land here after a rejection, or when their geometry needs evidenced review." />
        ) : (
          <div className="space-y-2">
            {units.map((u, i) => (
              <motion.button
                key={u.uuid}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03 }}
                onClick={() => {
                  setForm((f) => ({ ...f, local_code: u.local_code }))
                  loadHistory(u.local_code)
                }}
                className="block w-full text-left"
              >
                <Card className={`flex items-center justify-between p-3.5 transition ${form.local_code === u.local_code ? 'ring-1 ring-accent-blue/50' : ''}`}>
                  <div>
                    <p className="font-mono text-sm font-medium text-ink-primary">{u.local_code}</p>
                    <p className="text-[11px] text-ink-muted">{classMeta(u.su_class).label}</p>
                  </div>
                  <Badge color="#fab219" pulse>
                    DEGRADED
                  </Badge>
                </Card>
              </motion.button>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-4 lg:col-span-3">
        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-ink-primary">Record a review decision</h2>
          <div className="space-y-3">
            <Field label="Spatial unit local_code" required>
              <input
                className={`${inputClass} font-mono`}
                value={form.local_code}
                onChange={(e) => {
                  setForm({ ...form, local_code: e.target.value })
                }}
                onBlur={() => loadHistory(form.local_code)}
                placeholder="F05-U501"
              />
            </Field>
            <Field label="Reviewer label" required hint="Prototype metadata — not an authenticated identity">
              <input className={inputClass} value={form.reviewer_label} onChange={(e) => setForm({ ...form, reviewer_label: e.target.value })} placeholder="Site surveyor / junior engineer" />
            </Field>
            <Field label="Reason" required>
              <input className={inputClass} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="Field-verified against approved plan" />
            </Field>
            <label className="flex items-center gap-2 text-xs text-ink-secondary">
              <input
                type="checkbox"
                checked={form.release}
                onChange={(e) => setForm({ ...form, release: e.target.checked })}
                className="h-3.5 w-3.5 rounded border-hairline accent-accent-blue"
              />
              Release this unit's review block (requires an APPROVED decision + evidence)
            </label>
            {form.release && (
              <Field label="Evidence reference" required hint="e.g. site-visit report id, survey doc">
                <input className={inputClass} value={form.evidence_ref} onChange={(e) => setForm({ ...form, evidence_ref: e.target.value })} />
              </Field>
            )}
            <div className="flex gap-2 pt-1">
              <Button variant="success" icon={ClipboardCheck} loading={busy} onClick={() => submit('APPROVED')} className="flex-1">
                Approve
              </Button>
              <Button variant="danger" icon={ClipboardX} loading={busy} onClick={() => submit('REJECTED')} className="flex-1">
                Reject
              </Button>
            </div>
            <p className="flex items-start gap-1.5 text-[11px] text-ink-muted">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              Approval alone never releases the block — only APPROVED + release + evidence does, and only for this one
              unit. Deterministic validation then decides VALID or INVALID.
            </p>
          </div>
        </Card>

        {history !== null && (
          <Card className="p-5">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-primary">
              <History size={14} className="text-ink-muted" /> Review history
            </h2>
            {history.length === 0 ? (
              <p className="text-xs text-ink-muted">No decisions recorded yet for this unit.</p>
            ) : (
              <ul className="space-y-2">
                {history.map((h) => (
                  <li key={h.id} className="rounded-lg bg-black/[0.03] px-3 py-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className={h.decision === 'APPROVED' ? 'font-medium text-status-good' : 'font-medium text-status-critical'}>{h.decision}</span>
                      <span className="text-ink-muted">{formatDate(h.created_at)}</span>
                    </div>
                    <p className="mt-0.5 text-ink-secondary">{h.reviewer_label} — {h.reason}</p>
                    {h.released_block && <p className="mt-0.5 text-[11px] text-accent-blue">Block released · {h.evidence_ref}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}
