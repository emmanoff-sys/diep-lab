'use client';
import { useEffect } from 'react';

// Phase 11C — register the PWA service worker so the portal is installable
// ("Add to Home Screen") and launches offline as an app.
export default function ServiceWorkerRegister() {
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
  }, []);
  return null;
}
