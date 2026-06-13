// DIEP PWA service worker (Phase 11C).
// App-shell caching for offline launch + installability. API calls (/api/diep/*)
// are network-first and NEVER cached (live telemetry/commands must not be stale).
const CACHE = 'diep-shell-v1';
const SHELL = ['/', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Never cache the API (live data + mutations).
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(e.request));
    return;
  }
  // App shell: cache-first, fall back to network, then to the cached root (offline).
  e.respondWith(
    caches.match(e.request).then((hit) =>
      hit || fetch(e.request).catch(() => caches.match('/'))
    )
  );
});
