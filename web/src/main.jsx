import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import { applyTokens } from './design/tokens.js'
import { parseReport } from './lib/link.js'
import './styles/app.css'
import App from './App.jsx'

applyTokens()

// ?report=<result id> is the printable area report; anything else is the map.
const report = parseReport(window.location.search)
const ReportPage = lazy(() => import('./report/ReportPage.jsx'))

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      {report
        ? <Suspense fallback={null}><ReportPage resultId={report.resultId} name={report.name} /></Suspense>
        : <App />}
    </MotionConfig>
  </StrictMode>,
)
