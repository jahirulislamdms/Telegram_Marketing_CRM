import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { applyTheme } from './lib/theme'
import { useAuth } from './store/auth'
import './index.css'

// Apply the signed-in user's saved theme on first paint.
const persistedUser = useAuth.getState().user
applyTheme(persistedUser?.theme ?? 'dark')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
