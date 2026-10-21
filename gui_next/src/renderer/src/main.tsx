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
import { ensureLanguage } from './i18n'
import { useSettingsStore } from './store'

// Platform class on <html> for OS-specific rendering tweaks (see index.css).
document.documentElement.classList.add(`platform-${window.api.platform}`)

// Apply persisted (or default) theme before React mounts to avoid FOUC.
applyTheme(loadTheme())

// The window opens while Flask is still booting (main process); mount once it
// answers so the screens' first fetches don't fail. Bundle parse, theme and the
// IndexedDB cache read (App.tsx) have already overlapped the backend's startup.
// The saved language's locale chunk loads in the same wait, so a non-English UI
// doesn't paint in English first.
const backendReady = window.api?.backendReady?.() ?? Promise.resolve(true)
void Promise.all([
  backendReady.catch(() => false),
  ensureLanguage(useSettingsStore.getState().language).catch(() => {}),
]).then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  )
})
