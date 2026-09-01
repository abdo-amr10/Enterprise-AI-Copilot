import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import MainLayout from './layout/MainLayout.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import './styles/base.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider><MainLayout /></AuthProvider>
  </StrictMode>,
)
