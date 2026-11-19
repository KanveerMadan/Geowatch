import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import { applyTokens } from './design/tokens.js'
import { routeOf } from './lib/route.js'
import './styles/app.css'

applyTokens()

// One route per page, each its own chunk: the public pages never load the
// map. ?report=<result id> is the printable area report wherever it appears;
// a bare /?bbox= link (the explorer's old permanent form) opens the explorer.
const PAGES = {
  landing: lazy(() => import('./site/Landing.jsx')),
  gallery: lazy(() => import('./site/Gallery.jsx')),
  honesty: lazy(() => import('./site/Honesty.jsx')),
  notfound: lazy(() => import('./site/NotFound.jsx')),
  explore: lazy(() => import('./App.jsx')),
  report: lazy(() => import('./report/ReportPage.jsx')),
}

const route = routeOf(window.location.pathname, window.location.search)
const Page = PAGES[route.page]
const props = route.report ? { resultId: route.report.resultId, name: route.report.name } : {}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <Suspense fallback={null}><Page {...props} /></Suspense>
    </MotionConfig>
  </StrictMode>,
)
