import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './skin-refinement.css'
import './tablet.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
