import React, { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  MapPinned,
  UploadCloud,
  Boxes,
  Box,
  ShieldCheck,
  Scale,
  ClipboardCheck,
  DownloadCloud,
  ChevronDown,
  Menu,
  X,
  Activity,
  WifiOff,
} from 'lucide-react'
import clsx from '../../lib/clsx.js'
import { getHealth, listSites } from '../../lib/api.js'
import { useLive } from '../../lib/LiveContext.jsx'
import AuroraBackground from './AuroraBackground.jsx'

export const NAV_ITEMS = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'sites', label: 'Sites', icon: MapPinned },
  { key: 'import', label: 'Import & Process', icon: UploadCloud },
  { key: 'units', label: 'Spatial Units', icon: Boxes },
  { key: 'viewer', label: '3D Model', icon: Box, highlight: true },
  { key: 'validation', label: 'Validation', icon: ShieldCheck },
  { key: 'rights', label: 'Rights & Parties', icon: Scale },
  { key: 'review', label: 'Review Queue', icon: ClipboardCheck },
  { key: 'export', label: 'Export', icon: DownloadCloud },
]

function HealthPill() {
  const [state, setState] = useState('checking')
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const res = await getHealth()
        if (!cancelled) {
          setState('online')
          setDetail(res)
        }
      } catch {
        if (!cancelled) setState('offline')
      }
    }
    poll()
    const id = setInterval(poll, 20000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const tone =
    state === 'online'
      ? { dot: 'bg-status-good', text: 'text-status-good', label: 'All steady' }
      : state === 'offline'
        ? { dot: 'bg-status-critical', text: 'text-status-critical', label: "Can't reach the backend" }
        : { dot: 'bg-ink-muted', text: 'text-ink-muted', label: 'Getting ready…' }

  return (
    <div
      className="flex items-center gap-2 rounded-full border border-hairline bg-black/[0.03] px-3 py-1.5 text-xs"
      title={detail ? `PostGIS ${detail.postgis}` : undefined}
    >
      <span className={clsx('relative h-1.5 w-1.5 rounded-full', tone.dot, state === 'online' && 'animate-pulse-glow')}>
        {state === 'online' && (
          <motion.span
            className="absolute -inset-1 rounded-full bg-status-good/50"
            animate={{ scale: [1, 2.1, 1], opacity: [0.55, 0, 0.55] }}
            transition={{ duration: 2.2, repeat: Infinity, ease: 'easeOut' }}
          />
        )}
      </span>
      <span className={tone.text}>{tone.label}</span>
    </div>
  )
}

function SiteSelector({ siteId, onChange }) {
  const [sites, setSites] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    listSites()
      .then((res) => setSites(res.sites || []))
      .catch(() => setSites([]))
  }, [siteId])

  const current = sites.find((s) => s.id === siteId)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg border border-hairline bg-black/[0.03] px-3 py-1.5 text-xs text-ink-secondary transition hover:border-accent-blue/40 hover:text-ink-primary"
      >
        <MapPinned size={13} />
        <span className="max-w-[10rem] truncate">{current ? current.name : sites.length ? 'All sites' : 'No sites yet'}</span>
        <ChevronDown size={13} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="glass absolute right-0 z-20 mt-1.5 w-56 rounded-lg border border-hairline p-1 shadow-panel">
            <button
              onClick={() => {
                onChange(null)
                setOpen(false)
              }}
              className={clsx(
                'block w-full truncate rounded-md px-2.5 py-1.5 text-left text-xs hover:bg-black/[0.06]',
                !siteId ? 'text-accent-blue' : 'text-ink-secondary',
              )}
            >
              All sites (demo + everything)
            </button>
            {sites.map((s) => (
              <button
                key={s.id}
                onClick={() => {
                  onChange(s.id)
                  setOpen(false)
                }}
                className={clsx(
                  'block w-full truncate rounded-md px-2.5 py-1.5 text-left text-xs hover:bg-black/[0.06]',
                  siteId === s.id ? 'text-accent-blue' : 'text-ink-secondary',
                )}
              >
                {s.name}
              </button>
            ))}
            {!sites.length && <p className="px-2.5 py-1.5 text-xs text-ink-muted">Create a site to see it here.</p>}
          </div>
        </>
      )}
    </div>
  )
}

function timeAgo(ts) {
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - ts))
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  return `${hours}h ago`
}

// The header's live-activity pill: a small connection dot plus a dropdown
// feed of what's actually happening on the backend right now, streamed over
// SSE. This is what makes "real-time" visible rather than just claimed —
// seed the demo in one tab and this updates without anyone refreshing.
function LiveIndicator() {
  const { status, events } = useLive()
  const [open, setOpen] = useState(false)
  const [, forceTick] = useState(0)

  // Re-render every few seconds purely so the "12s ago" labels stay fresh
  // while the panel is open.
  useEffect(() => {
    if (!open) return
    const id = setInterval(() => forceTick((n) => n + 1), 4000)
    return () => clearInterval(id)
  }, [open])

  const tone =
    status === 'live'
      ? { dot: 'bg-status-good', text: 'text-status-good', label: 'Live' }
      : status === 'connecting'
        ? { dot: 'bg-ink-muted', text: 'text-ink-muted', label: 'Connecting…' }
        : { dot: 'bg-status-warning', text: 'text-ink-primary', label: 'Reconnecting…' }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-lg border border-hairline bg-black/[0.03] px-3 py-1.5 text-xs text-ink-secondary transition hover:border-accent-blue/40 hover:text-ink-primary"
        title="What's happening right now"
      >
        {status === 'live' ? (
          <span className="relative flex h-2 w-2">
            <motion.span
              className="absolute inset-0 rounded-full bg-status-good/50"
              animate={{ scale: [1, 2.4, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeOut' }}
            />
            <span className="relative h-2 w-2 rounded-full bg-status-good" />
          </span>
        ) : (
          <WifiOff size={12} className={tone.text} />
        )}
        <span className={tone.text}>{tone.label}</span>
        <Activity size={13} className="text-ink-muted" />
      </button>
      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: -6, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6, scale: 0.98 }}
              transition={{ duration: 0.15 }}
              className="glass absolute right-0 z-20 mt-1.5 w-80 max-h-[24rem] overflow-y-auto rounded-lg border border-hairline p-2 shadow-panel"
            >
              <p className="px-2 py-1.5 text-xs font-semibold text-ink-secondary">Live activity</p>
              {events.length === 0 ? (
                <p className="px-2 py-3 text-xs text-ink-muted">
                  Nothing yet — actions across the workspace (seeding, imports, reviews, validation) will show up
                  here the moment they happen.
                </p>
              ) : (
                <ul className="space-y-0.5">
                  <AnimatePresence initial={false}>
                    {events.map((e) => (
                      <motion.li
                        key={e.id}
                        initial={{ opacity: 0, x: -8 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.2 }}
                        className="rounded-md px-2 py-1.5 text-xs text-ink-secondary hover:bg-black/[0.04]"
                      >
                        <p className="text-ink-primary">{e.text}</p>
                        <p className="mt-0.5 text-[10px] text-ink-muted">{timeAgo(e.ts)}</p>
                      </motion.li>
                    ))}
                  </AnimatePresence>
                </ul>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  )
}

export function Shell({ active, onNavigate, siteId, onSiteChange, children }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const activeItem = NAV_ITEMS.find((i) => i.key === active)

  return (
    <div className="relative flex min-h-screen flex-col">
      <AuroraBackground />
      <div className="relative z-10 flex flex-1">
        {/* Sidebar (desktop) */}
        <aside className="glass sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-hairline lg:flex">
          <Brand />
          <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3">
            {NAV_ITEMS.map((item) => (
              <NavButton key={item.key} item={item} active={active === item.key} onClick={() => onNavigate(item.key)} />
            ))}
          </nav>
          <div className="border-t border-hairline p-3">
            <HealthPill />
          </div>
        </aside>

        {/* Mobile sidebar */}
        {mobileOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/70" onClick={() => setMobileOpen(false)} />
            <motion.aside
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: 'spring', stiffness: 320, damping: 32 }}
              className="glass relative flex h-full w-64 flex-col border-r border-hairline"
            >
              <Brand onClose={() => setMobileOpen(false)} />
              <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3">
                {NAV_ITEMS.map((item) => (
                  <NavButton
                    key={item.key}
                    item={item}
                    active={active === item.key}
                    onClick={() => {
                      onNavigate(item.key)
                      setMobileOpen(false)
                    }}
                  />
                ))}
              </nav>
            </motion.aside>
          </div>
        )}

        <div className="flex min-h-screen flex-1 flex-col">
          <header className="glass sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-hairline px-4 py-3 lg:px-8 relative">
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-accent-blue/50 to-transparent" />
            <div className="flex items-center gap-3">
              <button
                className="rounded-md p-1.5 text-ink-secondary hover:bg-black/5 lg:hidden"
                onClick={() => setMobileOpen(true)}
              >
                <Menu size={18} />
              </button>
              <div>
                <h1 className="text-sm font-semibold text-ink-primary">{activeItem?.label}</h1>
                <p className="hidden text-xs text-ink-muted sm:block">Every property here, given a shape and a story.</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <LiveIndicator />
              <SiteSelector siteId={siteId} onChange={onSiteChange} />
            </div>
          </header>
          <main className="relative flex-1 px-4 py-6 lg:px-8 lg:py-8">{children}</main>
        </div>
      </div>
    </div>
  )
}

// The brand mark is three offset slabs, not an icon-in-a-rounded-square —
// it reads as strata (the word this product is named for) and doubles as
// the same motif the hero glyph and stat tiles build on.
function StrataMark({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="2" y="15" width="20" height="5" rx="1.5" fill="#2a78d6" />
      <rect x="4.5" y="9" width="15" height="5" rx="1.5" fill="#1baf7a" />
      <rect x="7" y="3" width="10" height="5" rx="1.5" fill="#4a3aa7" />
    </svg>
  )
}

function Brand({ onClose }) {
  return (
    <div className="flex items-center justify-between border-b border-hairline px-4 py-4">
      <div className="flex items-center gap-2.5">
        <StrataMark />
        <p className="font-serif text-[16px] font-semibold leading-tight tracking-tight text-ink-primary">Stratum</p>
      </div>
      {onClose && (
        <button onClick={onClose} className="rounded-md p-1 text-ink-muted hover:bg-black/5">
          <X size={16} />
        </button>
      )}
    </div>
  )
}

function NavButton({ item, active, onClick }) {
  const Icon = item.icon
  return (
    <motion.button
      onClick={onClick}
      whileHover={{ x: active ? 0 : 2 }}
      whileTap={{ scale: 0.97 }}
      className={clsx(
        'group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
        active ? 'text-ink-primary' : 'text-ink-secondary hover:bg-black/[0.05] hover:text-ink-primary',
      )}
    >
      {active && (
        <motion.span
          layoutId="nav-active"
          className="glass absolute inset-0 rounded-lg border border-accent-blue/20 bg-accent-blue/[0.06]"
          transition={{ type: 'spring', stiffness: 380, damping: 32 }}
        />
      )}
      <Icon size={16} className={clsx('relative z-10 transition-colors', active && 'text-accent-blue')} />
      <span className="relative z-10">{item.label}</span>
      {item.highlight && (
        <span className="relative z-10 ml-auto h-1.5 w-1.5 rounded-full bg-accent-violet animate-pulse-glow" />
      )}
    </motion.button>
  )
}
