import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Self-hosted, so the content security policy can keep fonts to our own origin.
import '@fontsource-variable/inter/opsz.css'
import '@fontsource-variable/newsreader/opsz.css'

import App from './App.tsx'
import './styles/index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
