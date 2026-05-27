import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { applyTheme, loadTheme } from './lib/tokens'

// Apply persisted (or default) theme before React mounts to avoid FOUC.
applyTheme(loadTheme())

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
