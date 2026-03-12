const SW_VERSION = 'rg-arls-sw-v1773305601';
const SHELL_CACHE = `${SW_VERSION}-shell`;
const STATIC_CACHE = `${SW_VERSION}-static`;
const ACTIVE_CACHES = new Set([SHELL_CACHE, STATIC_CACHE]);

const SHELL_ASSETS = [
  './',
  './index.html',
  './config.js',
  './manifest.json',
  './css/styles.css',
  './js/app.js',
];

function isCacheableStatic(pathname) {
  return /\.(?:css|js|json|png|jpg|jpeg|svg|webp|ico|woff2?)$/i.test(pathname);
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const shell = await caches.open(SHELL_CACHE);
    await shell.addAll(SHELL_ASSETS);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys.map((key) => (ACTIVE_CACHES.has(key) ? Promise.resolve() : caches.delete(key))),
    );
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  const msgType = event?.data?.type;
  if (msgType === 'SKIP_WAITING') {
    self.skipWaiting();
    return;
  }
  if (msgType === 'CLEAR_APP_CACHE') {
    event.waitUntil((async () => {
      const keys = await caches.keys();
      await Promise.all(keys.map((key) => caches.delete(key)));
    })());
  }
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;

  const isShellRequest = url.pathname === '/' || url.pathname.endsWith('/index.html');
  const isStaticRequest = isCacheableStatic(url.pathname);
  if (!isShellRequest && !isStaticRequest) return;

  const targetCache = isStaticRequest ? STATIC_CACHE : SHELL_CACHE;

  event.respondWith((async () => {
    const cache = await caches.open(targetCache);
    try {
      const fromNetwork = await fetch(req);
      if (fromNetwork && fromNetwork.ok) {
        cache.put(req, fromNetwork.clone());
      }
      return fromNetwork;
    } catch {
      const cached = await cache.match(req);
      if (cached) return cached;
    }

    if (isShellRequest) {
      const fallback = await caches.match('./index.html');
      if (fallback) return fallback;
    }

    return new Response('offline', { status: 503, statusText: 'offline' });
  })());
});
