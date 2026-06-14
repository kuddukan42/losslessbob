import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

// Self-hosted fonts (avoids relying on a live fonts.googleapis.com fetch,
// which can silently fall back to system fonts on offline/firewalled Windows installs).
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/inter/800.css'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-sans/700.css'
import '@fontsource/source-sans-3/400.css'
import '@fontsource/source-sans-3/500.css'
import '@fontsource/source-sans-3/600.css'
import '@fontsource/source-sans-3/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/600.css'

import './index.css'
import { applyTheme, loadTheme } from './lib/tokens'
import './i18n'

// Platform class on <html> for OS-specific rendering tweaks (see index.css).
document.documentElement.classList.add(`platform-${window.api.platform}`)

// Apply persisted (or default) theme before React mounts to avoid FOUC.
applyTheme(loadTheme())

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
