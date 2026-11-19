/** Keeps the installed timetable on the device so the app opens and answers
 *  offline. One database is kept: the one in use.
 *
 *  Cache Storage when the page is a secure context; IndexedDB otherwise
 *  (Cache Storage does not exist on plain-HTTP origins, e.g. a phone opening
 *  the dev server by LAN address). */
import type { Manifest } from './manifest';

const CACHE = 'rahi-timetable-v1';
const DB_KEY = '/__timetable/db.sqlite';
const MANIFEST_KEY = '/__timetable/manifest.json';
const CHECKED_KEY = 'rahi.timetable.checkedAt';
const IDB = 'rahi-timetable';

export interface Installed {
	manifest: Manifest;
	bytes: Uint8Array;
}

const useCaches = () => 'caches' in globalThis && globalThis.isSecureContext;

function idb(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const req = indexedDB.open(IDB, 1);
		req.onupgradeneeded = () => req.result.createObjectStore('kv');
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
}

async function idbGet<T>(key: string): Promise<T | undefined> {
	const db = await idb();
	return new Promise((resolve, reject) => {
		const req = db.transaction('kv').objectStore('kv').get(key);
		req.onsuccess = () => resolve(req.result as T | undefined);
		req.onerror = () => reject(req.error);
	});
}

async function idbPutBoth(manifest: Manifest, bytes: Uint8Array): Promise<void> {
	const db = await idb();
	return new Promise((resolve, reject) => {
		const tx = db.transaction('kv', 'readwrite');
		tx.objectStore('kv').put(bytes, DB_KEY);
		tx.objectStore('kv').put(manifest, MANIFEST_KEY);
		tx.oncomplete = () => resolve();
		tx.onerror = () => reject(tx.error);
	});
}

export async function loadInstalled(): Promise<Installed | null> {
	if (useCaches()) {
		const cache = await caches.open(CACHE);
		const [m, d] = await Promise.all([cache.match(MANIFEST_KEY), cache.match(DB_KEY)]);
		if (!m || !d) return null;
		return { manifest: await m.json(), bytes: new Uint8Array(await d.arrayBuffer()) };
	}
	if (!('indexedDB' in globalThis)) return null;
	const [manifest, bytes] = await Promise.all([idbGet<Manifest>(MANIFEST_KEY), idbGet<Uint8Array>(DB_KEY)]);
	return manifest && bytes ? { manifest, bytes } : null;
}

export async function saveInstalled(manifest: Manifest, bytes: Uint8Array): Promise<void> {
	if (useCaches()) {
		const cache = await caches.open(CACHE);
		// Database first: a manifest is only ever stored next to its own bytes.
		await cache.put(DB_KEY, new Response(bytes as BlobPart, { headers: { 'content-type': 'application/vnd.sqlite3' } }));
		await cache.put(MANIFEST_KEY, new Response(JSON.stringify(manifest), { headers: { 'content-type': 'application/json' } }));
		return;
	}
	if ('indexedDB' in globalThis) await idbPutBoth(manifest, bytes); // one transaction: both or neither
}

export function lastChecked(): number {
	try {
		return Number(localStorage.getItem(CHECKED_KEY) ?? 0);
	} catch {
		return 0;
	}
}

export function markChecked(at = Date.now()): void {
	try {
		localStorage.setItem(CHECKED_KEY, String(at));
	} catch {
		/* private mode: we simply check again next time */
	}
}
