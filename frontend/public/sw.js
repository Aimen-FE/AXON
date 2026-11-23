const scope = new URL(self.registration.scope);
const scopeKey = encodeURIComponent(scope.pathname);
const SHELL_PREFIX = 'axon-shell:' + scopeKey + ':';
const SHELL_CACHE = SHELL_PREFIX + 'v10';
const STATIC_PORTAL = new URL(self.location.href).searchParams.has('static');
const PUBLIC_CACHE = scope.pathname === '/' ? 'axon-public-v1' : 'axon-public:' + scopeKey + ':v1';
const at = path => new URL(path, scope).href;
const PUBLIC_SNAPSHOT = at('axon-offline-public.json');
const SHELL = [
  'offline.html', 'public-view.css', 'public-view.js', 'manifest.webmanifest',
  'icon.svg', 'icon-192.png', 'icon-512.png', 'icon-maskable-512.png', 'apple-touch-icon.png',
  'fonts/AdwaitaSans-Regular.ttf',
];
const shellUrls = new Set(SHELL.map(at));
const assetPattern = /^assets\/[\w-]+-[\w-]{8,}\.(?:js|css|woff2?|ttf)$/;
const withoutSession = {credentials: 'omit', cache: 'no-store', redirect: 'error'};
const unavailable = (status = 404) => new Response('{}', {status});
const cacheable = response => response.ok && !response.redirected &&
  !/\b(?:private|no-store)\b/i.test(response.headers.get('cache-control') || '');

async function staticResponse(url) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(url);
  if (cached) return cached;
  const response = await fetch(url, withoutSession);
  if (cacheable(response)) await cache.put(url, response.clone());
  return response;
}

async function savePortal(cache, response) {
  if (!cacheable(response)) return;
  const html = await response.clone().text();
  const assets = [...html.matchAll(/\b(?:src|href)="([^"]+)"/g)].map(match => new URL(match[1], scope));
  const bundles = new Set(assets.filter(url => url.origin === scope.origin &&
    url.pathname.startsWith(scope.pathname) && assetPattern.test(url.pathname.slice(scope.pathname.length)))
    .map(url => url.href));
  if (!bundles.size) return;
  const responses = await Promise.all([...bundles].map(url => staticResponse(url)));
  if (!responses.every(cacheable)) return;
  await cache.put(scope.href, response);
}

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await cache.addAll(SHELL.map(path => new Request(at(path), withoutSession)));
    if (STATIC_PORTAL) await savePortal(cache, await fetch(scope.href, withoutSession));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      const outdated = key.startsWith('axon-shell') && key !== SHELL_CACHE;
      const legacyLocal = scope.pathname === '/' && /^axon-shell-v\d+$/.test(key);
      const oldPublicSnapshot = key.startsWith('axon-public');
      if (outdated || legacyLocal || oldPublicSnapshot) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

async function savePublicInformation() {
  const response = await fetch(at('api/public/info'), withoutSession);
  if (!response.ok) throw new Error('Información pública no disponible');
  const info = await response.json();
  const snapshot = {
    authorized_at: new Date().toISOString(),
    center: info.center ? {
      name: String(info.center.name).slice(0, 180),
      town: String(info.center.town).slice(0, 120),
    } : null,
    demo: !!info.demo,
    documents: (info.documents || []).slice(0, 100).map(doc => ({title: String(doc.title).slice(0, 180)})),
  };
  const cache = await caches.open(PUBLIC_CACHE);
  await cache.put(PUBLIC_SNAPSHOT, new Response(JSON.stringify(snapshot), {
    headers: {'Content-Type': 'application/json'},
  }));
}

async function readPublicInformation() {
  const cache = await caches.open(PUBLIC_CACHE);
  const cached = await cache.match(PUBLIC_SNAPSHOT);
  if (!cached) return unavailable();
  try {
    const {authorized_at} = await cached.clone().json();
    const age = Date.now() - Date.parse(authorized_at);
    if (Number.isFinite(age) && age >= 0 && age <= 7 * 86400000) return cached;
  } catch {
    // Discard obsolete or unreadable snapshots.
  }
  await cache.delete(PUBLIC_SNAPSHOT);
  return unavailable(410);
}

self.addEventListener('message', event => {
  if (STATIC_PORTAL || event.data?.type !== 'AUTHORIZE_PUBLIC_OFFLINE' || event.source?.type !== 'window') return;
  event.waitUntil(savePublicInformation().then(
    () => event.ports[0]?.postMessage({ok: true}),
    () => event.ports[0]?.postMessage({ok: false}),
  ));
});

async function navigation(event, isPortalHome) {
  try {
    const live = await fetch(event.request);
    if (!STATIC_PORTAL || live.ok) {
      if (STATIC_PORTAL && isPortalHome) {
        const copy = live.clone();
        event.waitUntil(caches.open(SHELL_CACHE).then(cache => savePortal(cache, copy)).catch(() => {}));
      }
      return live;
    }
  } catch {
    // Fall back to the public interface when the network is down.
  }
  const cache = await caches.open(SHELL_CACHE);
  if (STATIC_PORTAL && isPortalHome) {
    const portal = await cache.match(scope.href);
    if (portal) return portal;
  }
  return (await cache.match(at('offline.html'))) || Response.error();
}

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== scope.origin || !url.pathname.startsWith(scope.pathname)) return;
  const path = url.pathname.slice(scope.pathname.length);
  if (path === 'api' || path.startsWith('api/')) return;
  if (!STATIC_PORTAL && url.href === PUBLIC_SNAPSHOT) {
    event.respondWith(readPublicInformation());
    return;
  }
  if (request.mode === 'navigate') {
    event.respondWith(navigation(event, path === '' || path === 'index.html'));
    return;
  }
  if (!url.search && (shellUrls.has(url.href) || assetPattern.test(path))) {
    event.respondWith(staticResponse(url.href));
  }
});
