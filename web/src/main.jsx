import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import { applyTokens } from './design/tokens.js'
import './styles/app.css'
import App from './App.jsx'

applyTokens()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </StrictMode>,
)
