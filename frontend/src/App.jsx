import React, { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Shell } from './components/layout/Shell.jsx'
import { ToastProvider } from './lib/ToastContext.jsx'
import { LiveProvider } from './lib/LiveContext.jsx'
import OverviewPage from './pages/OverviewPage.jsx'
import SitesPage from './pages/SitesPage.jsx'
import ImportPage from './pages/ImportPage.jsx'
import UnitsPage from './pages/UnitsPage.jsx'
import ViewerPage from './pages/ViewerPage.jsx'
import ValidationPage from './pages/ValidationPage.jsx'
import RightsPage from './pages/RightsPage.jsx'
import ReviewPage from './pages/ReviewPage.jsx'
import ExportPage from './pages/ExportPage.jsx'

const PAGES = {
  overview: OverviewPage,
  sites: SitesPage,
  import: ImportPage,
  units: UnitsPage,
  viewer: ViewerPage,
  validation: ValidationPage,
  rights: RightsPage,
  review: ReviewPage,
  export: ExportPage,
}

function AppShell() {
  const [active, setActive] = useState('overview')
  const [siteId, setSiteId] = useState(null)
  const [focusCode, setFocusCode] = useState(null)

  // Some pages want to hand off a specific unit to another tab (e.g. "review
  // this unit" from the 3D viewer's selection panel jumps to the Review tab
  // with that local_code pre-filled).
  function navigateTo(key, code) {
    setActive(key)
    if (code !== undefined) setFocusCode(code)
  }

  const Page = PAGES[active] || OverviewPage

  return (
    <Shell active={active} onNavigate={navigateTo} siteId={siteId} onSiteChange={setSiteId}>
      <AnimatePresence mode="wait">
        <motion.div
          key={active}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
        >
          <Page
            siteId={siteId}
            onSiteChange={setSiteId}
            navigateTo={navigateTo}
            focusCode={focusCode}
            clearFocusCode={() => setFocusCode(null)}
          />
        </motion.div>
      </AnimatePresence>
    </Shell>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <LiveProvider>
        <AppShell />
      </LiveProvider>
    </ToastProvider>
  )
}
