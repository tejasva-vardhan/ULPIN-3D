import React, { useEffect, useRef } from 'react'
import { AnimatePresence, motion, animate } from 'framer-motion'
import { Loader2, X } from 'lucide-react'
import clsx from '../../lib/clsx.js'

// --- Card ------------------------------------------------------------------

export function Card({ children, className, as: As = 'div', ...rest }) {
  const MotionAs = typeof As === 'string' ? motion[As] : motion(As)
  return (
    <MotionAs
      whileHover={{ y: -2, transition: { duration: 0.18, ease: 'easeOut' } }}
      className={clsx(
        // A real frosted-glass surface (not just a flat translucent box): the
        // .glass recipe supplies the blur + saturation + inset top highlight,
        // and the asymmetric radius gives the card a shape of its own rather
        // than the generic uniform-rounded-rectangle every dashboard uses.
        'glass rounded-tl-[28px] rounded-tr-2xl rounded-br-[28px] rounded-bl-2xl border border-black/[0.06] shadow-panel ring-1 ring-inset ring-white/60 transition-shadow duration-200 hover:border-accent-blue/20 hover:shadow-panel-hover',
        className,
      )}
      {...rest}
    >
      {children}
    </MotionAs>
  )
}

// --- Button ------------------------------------------------------------

const BUTTON_VARIANTS = {
  primary: 'bg-accent-blue text-white hover:bg-accent-blue/90 shadow-[0_8px_20px_-8px_rgba(42,120,214,0.45)]',
  ghost: 'glass text-ink-primary hover:bg-black/[0.04] border border-black/[0.06]',
  danger: 'bg-status-critical/15 text-status-critical hover:bg-status-critical/25 border border-status-critical/30',
  success: 'bg-status-good/15 text-status-good hover:bg-status-good/25 border border-status-good/30',
  subtle: 'text-ink-secondary hover:text-ink-primary hover:bg-black/[0.06]',
}

export function Button({ variant = 'primary', className, disabled, loading, icon: Icon, children, ...rest }) {
  return (
    <motion.button
      disabled={disabled || loading}
      whileHover={disabled || loading ? undefined : { scale: 1.015 }}
      whileTap={disabled || loading ? undefined : { scale: 0.96 }}
      transition={{ type: 'spring', stiffness: 500, damping: 28 }}
      className={clsx(
        'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-medium transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:opacity-45',
        variant === 'primary' && 'sheen-hover',
        BUTTON_VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 size={15} className="animate-spin" /> : Icon ? <Icon size={15} /> : null}
      {children}
    </motion.button>
  )
}

// --- StatTile ----------------------------------------------------------

// Tailwind's JIT scanner only picks up class names it can see literally in the
// source, so tone classes are a static lookup table rather than a template
// literal like `bg-accent-${tone}` (which would compile to nothing).
const TONE_CLASSES = {
  blue: { chip: 'bg-accent-blue/10 text-accent-blue' },
  orange: { chip: 'bg-accent-orange/10 text-accent-orange' },
  aqua: { chip: 'bg-accent-aqua/10 text-accent-aqua' },
  yellow: { chip: 'bg-accent-yellow/10 text-accent-yellow' },
  magenta: { chip: 'bg-accent-magenta/10 text-accent-magenta' },
  green: { chip: 'bg-accent-green/10 text-accent-green' },
  violet: { chip: 'bg-accent-violet/10 text-accent-violet' },
  red: { chip: 'bg-accent-red/10 text-accent-red' },
}

// Counts up from 0 to the value's leading number on mount/change, keeping
// any non-numeric prefix/suffix (formatNumber/formatVolume return locale
// strings like "1,234" or "18.5 m\u00b3", not raw numbers). Falls back to a
// plain render for values with nothing numeric to count (e.g. "\u2014" while
// loading).
function CountingValue({ value }) {
  const ref = useRef(null)
  const str = value === null || value === undefined ? '' : String(value)
  const match = str.match(/^(-?[\d,]+(?:\.\d+)?)(.*)$/)
  const numeric = match ? Number(match[1].replace(/,/g, '')) : NaN
  const suffix = match ? match[2] : ''
  const canAnimate = Number.isFinite(numeric)

  useEffect(() => {
    if (!canAnimate || !ref.current) return
    const node = ref.current
    const controls = animate(0, numeric, {
      duration: 0.7,
      ease: 'easeOut',
      onUpdate: (v) => {
        node.textContent = Math.round(v).toLocaleString('en-IN') + suffix
      },
    })
    return () => controls.stop()
  }, [numeric, suffix, canAnimate])

  if (!canAnimate) return <>{value}</>
  return <span ref={ref}>{`0${suffix}`}</span>
}

export function StatTile({ label, value, hint, icon: Icon, tone = 'blue', delay = 0 }) {
  const toneClass = TONE_CLASSES[tone] || TONE_CLASSES.blue
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.35, ease: 'easeOut' }}
    >
      <Card className="relative overflow-hidden p-4">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</p>
          {Icon && (
            <span className={clsx('rounded-md p-1.5', toneClass.chip)}>
              <Icon size={14} />
            </span>
          )}
        </div>
        <p className="font-tabular mt-2 text-2xl font-semibold text-ink-primary">
          <CountingValue value={value} />
        </p>
        {hint && <p className="mt-1 text-xs text-ink-secondary">{hint}</p>}
      </Card>
    </motion.div>
  )
}

// --- Meter (single ratio against a limit) -------------------------------

export function Meter({ label, value, total, tone = 'good', hint }) {
  const pct = total > 0 ? Math.min(1, value / total) : 0
  const toneColor = { good: '#0ca30c', warning: '#fab219', critical: '#d03b3b', blue: '#2a78d6' }[tone] || '#2a78d6'
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-medium text-ink-secondary">{label}</span>
        <span className="font-tabular text-xs text-ink-muted">{hint ?? `${Math.round(pct * 100)}%`}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full" style={{ background: `${toneColor}22` }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: toneColor }}
          initial={{ width: 0 }}
          animate={{ width: `${pct * 100}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        />
      </div>
    </div>
  )
}

// --- Badge ---------------------------------------------------------------

export function Badge({ children, color = '#898781', pulse = false, className }) {
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 420, damping: 26 }}
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-5',
        className,
      )}
      style={{ borderColor: `${color}40`, color, background: `${color}18` }}
    >
      <span
        className={clsx('h-1.5 w-1.5 rounded-full', pulse && 'animate-pulse-glow')}
        style={{ background: color }}
      />
      {children}
    </motion.span>
  )
}

// --- Spinner -------------------------------------------------------------

export function Spinner({ size = 20, className }) {
  return <Loader2 size={size} className={clsx('animate-spin text-accent-blue', className)} />
}

// A small radar-sweep loader instead of a plain spinner glyph for full-page
// loading states \u2014 on-theme for a geospatial tool, and reads as "doing
// something" rather than a generic stock spinner.
export function PageSpinner({ label = 'Loading…' }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex h-64 flex-col items-center justify-center gap-4 text-ink-muted"
    >
      <div className="relative h-14 w-14">
        <div className="absolute inset-0 rounded-full border border-hairline" />
        <div className="absolute inset-2 rounded-full border border-hairline/70" />
        <div className="absolute inset-0 animate-radar-sweep rounded-full [background:conic-gradient(from_0deg,transparent_0deg,rgba(77,141,255,0.55)_60deg,transparent_90deg)]" />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-blue shadow-glow animate-pulse-glow" />
        </div>
      </div>
      <p className="text-sm">{label}</p>
    </motion.div>
  )
}

// --- EmptyState ----------------------------------------------------------

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-hairline px-8 py-16 text-center"
    >
      {Icon && (
        <motion.div
          animate={{ y: [0, -5, 0] }}
          transition={{ duration: 2.6, repeat: Infinity, ease: 'easeInOut' }}
          className="rounded-full bg-black/[0.04] p-3 text-ink-muted"
        >
          <Icon size={22} />
        </motion.div>
      )}
      <div>
        <p className="text-sm font-semibold text-ink-primary">{title}</p>
        {description && <p className="mx-auto mt-1 max-w-sm text-sm text-ink-secondary">{description}</p>}
      </div>
      {action}
    </motion.div>
  )
}

// --- Modal -----------------------------------------------------------------

export function Modal({ open, onClose, title, subtitle, children, width = 'max-w-lg' }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[150] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.94, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ type: 'spring', stiffness: 320, damping: 28 }}
            className={clsx(
              'glass relative max-h-[85vh] w-full overflow-y-auto rounded-2xl border border-black/[0.06] shadow-panel',
              width,
            )}
          >
            <div className="glass sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-hairline px-5 py-4">
              <div>
                <h3 className="text-sm font-semibold text-ink-primary">{title}</h3>
                {subtitle && <p className="mt-0.5 text-xs text-ink-secondary">{subtitle}</p>}
              </div>
              <button
                onClick={onClose}
                className="rounded-md p-1.5 text-ink-muted transition hover:bg-black/5 hover:text-ink-primary"
              >
                <X size={16} />
              </button>
            </div>
            <div className="px-5 py-4">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// --- Field (label + input wrapper for forms) ------------------------------

export function Field({ label, hint, children, required }) {
  return (
    <label className="block">
      <span className="mb-1 flex items-center gap-1 text-xs font-medium text-ink-secondary">
        {label}
        {required && <span className="text-status-critical">*</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-ink-muted">{hint}</span>}
    </label>
  )
}

export const inputClass =
  'w-full rounded-lg border border-hairline bg-black/[0.03] px-3 py-2 text-sm text-ink-primary placeholder:text-ink-muted focus:border-accent-blue/60 focus:outline-none focus:ring-2 focus:ring-accent-blue/20 transition'
