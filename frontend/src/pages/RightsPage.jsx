import React, { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { UserPlus, Building2, Scale, Plus } from 'lucide-react'
import { Card, Button, Field, inputClass, EmptyState, PageSpinner } from '../components/ui/primitives.jsx'
import { useToast } from '../lib/ToastContext.jsx'
import { createParty, createBaunit, createRRR, listRRR, listParties, listBaunits } from '../lib/api.js'
import { formatPercent, formatDate } from '../lib/format.js'

const RRR_TYPES = ['RIGHT', 'RESTRICTION', 'RESPONSIBILITY']
const PARTY_TYPES = ['person', 'organisation', 'association', 'authority']

export default function RightsPage({ siteId }) {
  const toast = useToast()
  const [rrr, setRrr] = useState(null)
  const [parties, setParties] = useState([])
  const [baunits, setBaunits] = useState([])

  const [partyForm, setPartyForm] = useState({ party_type: 'person', name: '' })
  const [baunitForm, setBaunitForm] = useState({ name: '', uid: '' })
  const [rrrForm, setRrrForm] = useState({
    local_code: '',
    baunit_id: '',
    party_id: '',
    rrr_type: 'RIGHT',
    share: '',
    claim_status: 'CLAIMED',
    evidence_ref: '',
    description: '',
  })
  const [busy, setBusy] = useState({})

  const load = useCallback(() => {
    listRRR(siteId).then((r) => setRrr(r.rrr)).catch(() => setRrr([]))
    listParties().then((r) => setParties(r.parties)).catch(() => setParties([]))
    listBaunits().then((r) => setBaunits(r.baunits)).catch(() => setBaunits([]))
  }, [siteId])

  useEffect(() => load(), [load])

  function setLoading(key, val) {
    setBusy((b) => ({ ...b, [key]: val }))
  }

  async function submitParty(e) {
    e.preventDefault()
    if (!partyForm.name.trim()) return toast.warning('Party name is required.')
    setLoading('party', true)
    try {
      await createParty(partyForm)
      toast.success(`${partyForm.name} added.`, { title: 'Party created' })
      setPartyForm({ party_type: 'person', name: '' })
      load()
    } catch (err) {
      toast.error(err.message, { title: 'Could not create party' })
    } finally {
      setLoading('party', false)
    }
  }

  async function submitBaunit(e) {
    e.preventDefault()
    setLoading('baunit', true)
    try {
      await createBaunit(baunitForm)
      toast.success('Administrative unit created.', { title: 'Baunit created' })
      setBaunitForm({ name: '', uid: '' })
      load()
    } catch (err) {
      toast.error(err.message, { title: 'Could not create baunit' })
    } finally {
      setLoading('baunit', false)
    }
  }

  async function submitRrr(e) {
    e.preventDefault()
    if (!siteId) return toast.warning('Select a site from the top bar first.')
    if (!rrrForm.local_code || !rrrForm.baunit_id || !rrrForm.party_id) {
      return toast.warning('Unit code, administrative unit and party are all required.')
    }
    setLoading('rrr', true)
    try {
      const payload = {
        site_id: siteId,
        local_code: rrrForm.local_code,
        baunit_id: rrrForm.baunit_id,
        party_id: rrrForm.party_id,
        rrr_type: rrrForm.rrr_type,
        claim_status: rrrForm.claim_status,
        description: rrrForm.description || undefined,
        evidence_ref: rrrForm.evidence_ref || undefined,
        share: rrrForm.share === '' ? undefined : Number(rrrForm.share),
      }
      await createRRR(payload)
      toast.success(`${rrrForm.rrr_type} recorded on ${rrrForm.local_code}.`, { title: 'Right recorded' })
      setRrrForm({ ...rrrForm, local_code: '', share: '', description: '', evidence_ref: '' })
      load()
    } catch (err) {
      toast.error(err.message, { title: 'Could not record right' })
    } finally {
      setLoading('rrr', false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-primary">
            <UserPlus size={15} className="text-accent-blue" /> New party
          </h2>
          <form onSubmit={submitParty} className="space-y-3">
            <Field label="Type">
              <select className={inputClass} value={partyForm.party_type} onChange={(e) => setPartyForm({ ...partyForm, party_type: e.target.value })}>
                {PARTY_TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </Field>
            <Field label="Name" required>
              <input className={inputClass} value={partyForm.name} onChange={(e) => setPartyForm({ ...partyForm, name: e.target.value })} placeholder="Allottee / organisation name" />
            </Field>
            <Button type="submit" variant="ghost" loading={busy.party} icon={Plus} className="w-full">
              Add party
            </Button>
          </form>
        </Card>

        <Card className="p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-primary">
            <Building2 size={15} className="text-accent-aqua" /> New administrative unit
          </h2>
          <form onSubmit={submitBaunit} className="space-y-3">
            <Field label="Name">
              <input className={inputClass} value={baunitForm.name} onChange={(e) => setBaunitForm({ ...baunitForm, name: e.target.value })} placeholder="e.g. Demo apartment scheme" />
            </Field>
            <Field label="UID" hint="Must be unique if supplied">
              <input className={`${inputClass} font-mono`} value={baunitForm.uid} onChange={(e) => setBaunitForm({ ...baunitForm, uid: e.target.value })} placeholder="BA-PUNE-01" />
            </Field>
            <Button type="submit" variant="ghost" loading={busy.baunit} icon={Plus} className="w-full">
              Add administrative unit
            </Button>
          </form>
        </Card>

        <Card className="p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-primary">
            <Scale size={15} className="text-accent-violet" /> Record a right
          </h2>
          <form onSubmit={submitRrr} className="space-y-3">
            <Field label="Spatial unit local_code" required>
              <input className={`${inputClass} font-mono`} value={rrrForm.local_code} onChange={(e) => setRrrForm({ ...rrrForm, local_code: e.target.value })} placeholder="F02-U201" />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Administrative unit" required>
                <select className={inputClass} value={rrrForm.baunit_id} onChange={(e) => setRrrForm({ ...rrrForm, baunit_id: e.target.value })}>
                  <option value="">Select…</option>
                  {baunits.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name || b.uid || b.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Party" required>
                <select className={inputClass} value={rrrForm.party_id} onChange={(e) => setRrrForm({ ...rrrForm, party_id: e.target.value })}>
                  <option value="">Select…</option>
                  {parties.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Type">
                <select className={inputClass} value={rrrForm.rrr_type} onChange={(e) => setRrrForm({ ...rrrForm, rrr_type: e.target.value })}>
                  {RRR_TYPES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </Field>
              <Field label="Share" hint="0–1, RIGHT only">
                <input className={`${inputClass} font-mono`} value={rrrForm.share} onChange={(e) => setRrrForm({ ...rrrForm, share: e.target.value })} placeholder="0.5" />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Claim status">
                <select className={inputClass} value={rrrForm.claim_status} onChange={(e) => setRrrForm({ ...rrrForm, claim_status: e.target.value })}>
                  <option value="CLAIMED">CLAIMED</option>
                  <option value="VERIFIED">VERIFIED</option>
                </select>
              </Field>
              <Field label="Evidence ref" hint="Required if VERIFIED">
                <input className={inputClass} value={rrrForm.evidence_ref} onChange={(e) => setRrrForm({ ...rrrForm, evidence_ref: e.target.value })} />
              </Field>
            </div>
            <Field label="Description">
              <input className={inputClass} value={rrrForm.description} onChange={(e) => setRrrForm({ ...rrrForm, description: e.target.value })} />
            </Field>
            <Button type="submit" loading={busy.rrr} icon={Plus} className="w-full">
              Record
            </Button>
          </form>
        </Card>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-ink-primary">Recorded rights</h2>
        {rrr === null ? (
          <PageSpinner label="Loading…" />
        ) : rrr.length === 0 ? (
          <EmptyState icon={Scale} title="No rights recorded yet" description="Use the form above to attach a RIGHT, RESTRICTION or RESPONSIBILITY to a spatial unit." />
        ) : (
          <Card className="overflow-hidden">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-hairline text-[10px] uppercase tracking-wide text-ink-muted">
                  <th className="px-4 py-2.5 font-medium">Unit</th>
                  <th className="px-4 py-2.5 font-medium">Type</th>
                  <th className="px-4 py-2.5 font-medium">Party</th>
                  <th className="px-4 py-2.5 font-medium">Share</th>
                  <th className="px-4 py-2.5 font-medium">Claim</th>
                  <th className="px-4 py-2.5 font-medium">Recorded</th>
                </tr>
              </thead>
              <tbody>
                {rrr.map((r, i) => (
                  <motion.tr key={r.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.02, 0.3) }} className="border-b border-hairline/60">
                    <td className="px-4 py-2.5 font-mono text-ink-primary">{r.local_code}</td>
                    <td className="px-4 py-2.5 text-ink-secondary">{r.rrr_type}</td>
                    <td className="px-4 py-2.5 text-ink-secondary">{r.party_name}</td>
                    <td className="px-4 py-2.5 font-tabular text-ink-secondary">{r.share !== null ? formatPercent(r.share) : '—'}</td>
                    <td className="px-4 py-2.5 text-ink-muted">{r.claim_status}</td>
                    <td className="px-4 py-2.5 text-ink-muted">{formatDate(r.created_at)}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  )
}
