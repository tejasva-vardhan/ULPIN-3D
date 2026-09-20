import React, { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { MapPinned, Plus, Copy } from 'lucide-react'
import { Card, Button, Field, inputClass, PageSpinner, EmptyState } from '../components/ui/primitives.jsx'
import { useToast } from '../lib/ToastContext.jsx'
import { createSite, listSites } from '../lib/api.js'
import { useLiveRefresh } from '../lib/LiveContext.jsx'

const EMPTY = { name: '', epsg: '4326', parent_ulpin: '', z_ref: 'LOCAL_SITE' }

export default function SitesPage({ onSiteChange }) {
  const toast = useToast()
  const [sites, setSites] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    listSites()
      .then((res) => setSites(res.sites))
      .catch(() => setSites([]))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useLiveRefresh(['site.created'], load)

  async function submit(e) {
    e.preventDefault()
    if (!form.name.trim() || !form.parent_ulpin.trim()) {
      toast.warning('Name and parent ULPIN are required.')
      return
    }
    setBusy(true)
    try {
      const res = await createSite({ ...form, epsg: Number(form.epsg) })
      toast.success(`${res.name} is ready for import.`, { title: 'Site created' })
      setForm(EMPTY)
      load()
    } catch (err) {
      toast.error(err.message, { title: 'Could not create site' })
    } finally {
      setBusy(false)
    }
  }

  function copyId(id) {
    navigator.clipboard?.writeText(id)
    toast.info('Site id copied to clipboard.')
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
      <Card className="p-5 lg:col-span-2">
        <h2 className="mb-1 text-sm font-semibold text-ink-primary">Register a site</h2>
        <p className="mb-4 text-xs text-ink-secondary">
          A site scopes everything that follows — datasets, spatial units and rights all attach to one site.
        </p>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Site name" required>
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Kothrud residential block"
            />
          </Field>
          <Field label="Parent ULPIN" required hint="14-character placeholder or real ULPIN. Never invented silently by the backend.">
            <input
              className={`${inputClass} font-mono`}
              value={form.parent_ulpin}
              onChange={(e) => setForm({ ...form, parent_ulpin: e.target.value })}
              placeholder="12AB34CD56EF78"
              maxLength={14}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Source EPSG" required hint="CRS of the geometry you'll import">
              <input
                className={`${inputClass} font-mono`}
                value={form.epsg}
                onChange={(e) => setForm({ ...form, epsg: e.target.value })}
                placeholder="4326"
              />
            </Field>
            <Field label="Height reference">
              <select className={inputClass} value={form.z_ref} onChange={(e) => setForm({ ...form, z_ref: e.target.value })}>
                <option value="LOCAL_SITE">LOCAL_SITE</option>
              </select>
            </Field>
          </div>
          <Button type="submit" loading={busy} icon={Plus} className="w-full">
            Create site
          </Button>
        </form>
      </Card>

      <div className="lg:col-span-3">
        {sites === null ? (
          <PageSpinner label="Loading sites…" />
        ) : sites.length === 0 ? (
          <EmptyState
            icon={MapPinned}
            title="No sites yet"
            description="Register your first site on the left to start importing geometry."
          />
        ) : (
          <div className="space-y-3">
            {sites.map((s, i) => (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
              >
                <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink-primary">{s.name}</p>
                    <p className="mt-0.5 font-mono text-[11px] text-ink-muted">
                      parent {s.parent_ulpin} · EPSG:{s.source_epsg} → EPSG:{s.storage_epsg} · {s.z_ref}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => copyId(s.id)}
                      className="flex items-center gap-1.5 rounded-md border border-hairline px-2.5 py-1 text-[11px] text-ink-muted hover:text-ink-primary"
                    >
                      <Copy size={12} /> id
                    </button>
                    <Button variant="ghost" onClick={() => onSiteChange?.(s.id)}>
                      Use this site
                    </Button>
                  </div>
                </Card>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
