import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { ErrorBoundary } from './components/common/ErrorBoundary'

const init = async () => {
  // Initialize mock in development if pywebview is missing
  if (import.meta.env.DEV && !window.pywebview) {
    try {
      const { initializeMock } = await import('./lib/mock');
      initializeMock();
    } catch (e) {
      console.warn("Failed to load PyWebView mock", e);
    }
  }

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </React.StrictMode>,
  )
};

init();
