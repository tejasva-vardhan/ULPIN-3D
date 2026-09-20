import React from 'react'

// A fixed, pointer-events-none backdrop mounted once behind the whole app:
// a barely-visible static grid for quiet texture. No colour washes or glow —
// this is a government records tool, not a marketing site, so the backdrop
// stays out of the way of the data.
export default function AuroraBackground() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <div className="bg-grid absolute inset-0 opacity-50 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)]" />
    </div>
  )
}
