/// <reference lib="webworker" />
/** Offline app shell. Built assets and static files are cached at install;
 *  navigations are network-first so a new deploy is picked up, falling back
 *  to the cached shell offline. The timetable database is not handled here:
 *  the app stores and updates it itself (src/lib/data). */
import { self } from '$app/service-worker';
import { immutable, assets, prerendered } from '$app/manifest';
import { version } from '$app/env';

const CACHE = `rahi-shell-${version}`;
const scope = new URL(self.registration.scope);
const url = (p: string) => new URL(p, scope).href;
const SHELL = url('404.html');
const PRECACHE = [...immutable, ...assets, ...prerendered].map((f) => url(f.path)).concat(SHELL);

self.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((cache) => cache.addAll(PRECACHE).catch(() => cache.addAll(PRECACHE.filter((u) => u !== SHELL))))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k.startsWith('rahi-shell-') && k !== CACHE).map((k) => caches.delete(k))))
			.then(() => self.clients.claim())
	);
});

self.addEventListener('fetch', (event) => {
	const req = event.request;
	if (req.method !== 'GET') return;
	const u = new URL(req.url);
	if (u.origin !== scope.origin) return; // timetable downloads etc.

	if (req.mode === 'navigate') {
		event.respondWith(
			(async () => {
				try {
					const res = await fetch(req);
					if (res.ok || res.status === 404) return res;
					throw new Error(String(res.status));
				} catch {
					const cache = await caches.open(CACHE);
					return (
						(await cache.match(req, { ignoreSearch: true })) ??
						(await cache.match(SHELL)) ??
						new Response('Offline', { status: 503 })
					);
				}
			})()
		);
		return;
	}

	event.respondWith(
		(async () => {
			const cache = await caches.open(CACHE);
			const hit = await cache.match(req);
			if (hit) return hit;
			const res = await fetch(req);
			if (res.ok && PRECACHE.includes(req.url)) void cache.put(req, res.clone());
			return res;
		})()
	);
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();
	event.waitUntil(
		self.clients.matchAll({ type: 'window' }).then((clients) => (clients[0] ? clients[0].focus() : self.clients.openWindow(scope.href)))
	);
});
