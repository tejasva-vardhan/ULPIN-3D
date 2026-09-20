import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { eventsUrl } from './api.js'

const LiveContext = createContext(null)

// Turns a raw server event into a short, plain-language sentence for the
// activity feed — the point of streaming this live is to feel like someone
// is actually working the site, not to expose an API log.
function describe(event) {
  const p = event.payload || {}
  switch (event.type) {
    case 'demo.seeded':
      return `Demo scene seeded — ${p.spatial_units ?? 'a few'} spatial units are ready to explore.`
    case 'demo.degraded':
      return `Ran the "missing plans" demo — ${p.whole_floor_units ?? 'some'} floors came back needing review.`
    case 'demo.overlap_fixed':
      return 'Cleaned up the seeded overlap — re-validating the affected unit.'
    case 'site.created':
      return `A new site was registered${p.name ? `: “${p.name}”` : ''}.`
    case 'dataset.processed':
      return `Dataset processed — ${p.count ?? 'new'} spatial units created.`
    case 'building.processed':
      return `Building elevation processed${p.method ? ` (${p.method})` : ''}.`
    case 'rrr.recorded':
      return `A ${(p.rrr_type || 'right').toLowerCase()} was recorded against a spatial unit.`
    case 'unit.reviewed':
      return `${p.local_code || 'A unit'} was reviewed — ${(p.decision || 'decision recorded').toLowerCase()}${p.topology_status ? `, now ${p.topology_status}` : ''}.`
    case 'unit.issued':
      return `${p.local_code || 'A unit'} was issued a proposed 3D ULPIN.`
    case 'unit.withdrawn':
      return `${p.local_code || 'A unit'} was withdrawn.`
    case 'validation.run':
      return `Validation ran — ${p.error_count ?? 0} blocking issue${p.error_count === 1 ? '' : 's'} found.`
    default:
      return event.type
  }
}

export function LiveProvider({ children }) {
  const [status, setStatus] = useState('connecting') // connecting | live | offline
  const [events, setEvents] = useState([])
  const listenersRef = useRef(new Set())

  useEffect(() => {
    let closed = false
    let source
    try {
      source = new EventSource(eventsUrl())
    } catch {
      setStatus('offline')
      return
    }

    source.onopen = () => {
      if (!closed) setStatus('live')
    }
    source.onerror = () => {
      // The native EventSource keeps retrying on its own; we just reflect
      // that we're between connections until the next onopen fires.
      if (!closed) setStatus('offline')
    }
    source.onmessage = (raw) => {
      let event
      try {
        event = JSON.parse(raw.data)
      } catch {
        return
      }
      const entry = { ...event, id: `${event.ts}-${Math.random().toString(36).slice(2, 8)}`, text: describe(event) }
      setEvents((prev) => [entry, ...prev].slice(0, 30))
      listenersRef.current.forEach((fn) => fn(entry))
    }

    return () => {
      closed = true
      source.close()
    }
  }, [])

  const api = useMemo(
    () => ({
      status,
      events,
      // Register a callback fired on every incoming event; returns an
      // unsubscribe function. Pages use this to refetch their own data
      // when something relevant streams in, instead of polling blind.
      onEvent: (fn) => {
        listenersRef.current.add(fn)
        return () => listenersRef.current.delete(fn)
      },
    }),
    [status, events],
  )

  return <LiveContext.Provider value={api}>{children}</LiveContext.Provider>
}

export function useLive() {
  const ctx = useContext(LiveContext)
  if (!ctx) throw new Error('useLive must be used within a LiveProvider')
  return ctx
}

// Convenience hook: re-run `onRelevantEvent` whenever a streamed event's
// type matches one of `types`. Used by pages that want to refetch as soon
// as something changes, rather than only on a timer or manual refresh.
export function useLiveRefresh(types, onRelevantEvent) {
  const { onEvent } = useLive()
  const typesRef = useRef(types)
  typesRef.current = types
  const cbRef = useRef(onRelevantEvent)
  cbRef.current = onRelevantEvent

  useEffect(() => {
    return onEvent((event) => {
      if (typesRef.current.includes(event.type)) cbRef.current(event)
    })
  }, [onEvent])
}
