import React, { createContext, useCallback, useContext, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-react'

const ToastContext = createContext(null)

const TONES = {
  success: { icon: CheckCircle2, ring: 'ring-status-good/30', iconColor: 'text-status-good' },
  error: { icon: XCircle, ring: 'ring-status-critical/30', iconColor: 'text-status-critical' },
  warning: { icon: AlertTriangle, ring: 'ring-status-warning/30', iconColor: 'text-status-warning' },
  info: { icon: Info, ring: 'ring-accent-blue/30', iconColor: 'text-accent-blue' },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const counter = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (message, tone = 'info', opts = {}) => {
      const id = ++counter.current
      const toast = { id, message, tone, title: opts.title }
      setToasts((prev) => [...prev.slice(-3), toast])
      window.setTimeout(() => dismiss(id), opts.duration ?? 5200)
      return id
    },
    [dismiss],
  )

  const api = {
    push,
    dismiss,
    success: (m, o) => push(m, 'success', o),
    error: (m, o) => push(m, 'error', { duration: 7000, ...o }),
    warning: (m, o) => push(m, 'warning', o),
    info: (m, o) => push(m, 'info', o),
  }

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[200] flex w-full max-w-sm flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((t) => {
            const tone = TONES[t.tone] || TONES.info
            const Icon = tone.icon
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, y: 16, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 40, scale: 0.96, transition: { duration: 0.18 } }}
                transition={{ type: 'spring', stiffness: 420, damping: 32 }}
                className={`pointer-events-auto glass flex items-start gap-3 rounded-xl border border-hairline px-4 py-3 shadow-panel ring-1 ${tone.ring}`}
              >
                <Icon size={18} className={`mt-0.5 shrink-0 ${tone.iconColor}`} />
                <div className="min-w-0 flex-1">
                  {t.title && <p className="text-sm font-semibold text-ink-primary">{t.title}</p>}
                  <p className="break-words text-sm text-ink-secondary">{t.message}</p>
                </div>
                <button
                  onClick={() => dismiss(t.id)}
                  className="shrink-0 rounded-md p-1 text-ink-muted transition hover:bg-black/5 hover:text-ink-primary"
                  aria-label="Dismiss notification"
                >
                  <X size={14} />
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
