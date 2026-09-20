import React, { useEffect, useState } from 'react'
import { AlertTriangle, ExternalLink, FileCheck2, Scale, History } from 'lucide-react'
import { Modal, Badge, Meter, PageSpinner } from '../ui/primitives.jsx'
import { classMeta, statusMeta, formatMeters, formatVolume, formatDate, formatPercent } from '../../lib/format.js'
import { getRecordByCode, recordHtmlUrl } from '../../lib/api.js'
import { useToast } from '../../lib/ToastContext.jsx'

export default function RecordCard({ localCode, siteId, open, onClose }) {
  const toast = useToast()
  const [rec, setRec] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !localCode) return
    setLoading(true)
    setRec(null)
    getRecordByCode(localCode, siteId)
      .then(setRec)
      .catch((e) => toast.error(e.message, { title: 'Could not load record' }))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, localCode, siteId])

  const cls = rec ? classMeta(rec.su_class) : null
  const status = rec ? statusMeta(rec.topology_status) : null

  return (
    <Modal open={open} onClose={onClose} title={rec ? rec.local_code : localCode} subtitle={rec?.display_id} width="max-w-2xl">
      {loading && <PageSpinner label="Loading record…" />}
      {rec && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge color={cls.color}>{cls.label}</Badge>
            <Badge color={status.color} pulse={rec.topology_status === 'DEGRADED'}>
              {status.label}
            </Badge>
            <Badge color="#898781">{rec.geom_origin}</Badge>
            <Badge color="#898781">v{String(rec.version).padStart(2, '0')}</Badge>
            <a
              href={recordHtmlUrl(rec.local_code, siteId)}
              target="_blank"
              rel="noreferrer"
              className="ml-auto inline-flex items-center gap-1 text-[11px] text-accent-blue hover:underline"
            >
              Printable record <ExternalLink size={11} />
            </a>
          </div>

          <div className="rounded-lg border border-status-warning/25 bg-status-warning/[0.06] p-3 text-[11px] leading-relaxed text-ink-primary">
            <AlertTriangle size={12} className="mb-1 inline-block text-status-warning" /> {rec.note}
          </div>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs sm:grid-cols-3">
            <Kv label="Height range" value={`${formatMeters(rec.zmin)} → ${formatMeters(rec.zmax)}`} />
            <Kv label="Volume" value={formatVolume(rec.volume_m3)} />
            <Kv label="Parent ULPIN" value={rec.parent_ulpin} mono />
            <Kv label="Confidence" value={rec.confidence !== null ? formatPercent(rec.confidence) : '—'} />
            <Kv label="Status" value={rec.status} />
            <Kv label="Internal UUID" value={rec.uuid} mono truncate />
          </dl>

          {rec.confidence !== null && rec.confidence !== undefined && (
            <Meter label="Geometry confidence" value={rec.confidence} total={1} tone={rec.confidence > 0.6 ? 'good' : 'warning'} />
          )}

          <Section title="Rights, restrictions & responsibilities" icon={Scale}>
            {rec.rrr?.length ? (
              <ul className="space-y-1.5">
                {rec.rrr.map((r) => (
                  <li key={r.id} className="flex items-center justify-between rounded-lg bg-black/[0.03] px-3 py-1.5 text-xs">
                    <span>
                      <span className="font-medium text-ink-primary">{r.rrr_type}</span>
                      <span className="text-ink-muted"> · {r.party_name}</span>
                    </span>
                    <span className="font-tabular text-ink-secondary">{r.share !== null ? formatPercent(r.share) : r.claim_status}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-ink-muted">No rights recorded on this space.</p>
            )}
          </Section>

          <Section title="Review history" icon={History}>
            {rec.reviews?.length ? (
              <ul className="space-y-1.5">
                {rec.reviews.map((r) => (
                  <li key={r.id} className="rounded-lg bg-black/[0.03] px-3 py-1.5 text-xs">
                    <div className="flex items-center justify-between">
                      <span className={r.decision === 'APPROVED' ? 'text-status-good' : 'text-status-critical'}>{r.decision}</span>
                      <span className="text-ink-muted">{formatDate(r.created_at)}</span>
                    </div>
                    <p className="mt-0.5 text-ink-secondary">{r.reviewer_label} — {r.reason}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-ink-muted">No review decisions recorded.</p>
            )}
          </Section>

          {rec.source && (
            <Section title="Source evidence" icon={FileCheck2}>
              <p className="text-xs text-ink-secondary">
                {rec.source.filename} · EPSG:{rec.source.epsg} · checksum{' '}
                <span className="font-mono text-ink-muted">{rec.source.checksum_sha256?.slice(0, 12)}…</span>
              </p>
            </Section>
          )}
        </div>
      )}
    </Modal>
  )
}

function Kv({ label, value, mono, truncate }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className={`mt-0.5 text-ink-primary ${mono ? 'font-mono text-[11px]' : ''} ${truncate ? 'truncate' : ''}`}>{value ?? '—'}</dd>
    </div>
  )
}

function Section({ title, icon: Icon, children }) {
  return (
    <div>
      <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-ink-primary">
        <Icon size={13} className="text-ink-muted" /> {title}
      </h4>
      {children}
    </div>
  )
}
