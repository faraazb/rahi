/** The timetable the app is using, and how it stays current.
 *
 *  Start-up opens the copy already on the device (works offline). Then, at
 *  most every few hours, the manifest of the latest release is fetched; if
 *  its version differs, the database is downloaded, checked against both
 *  SHA-256 sums in the manifest, opened to prove it is readable, and only
 *  then swapped in and stored. A failed or partial download never replaces
 *  a working timetable. */
import type { Database } from 'sql.js';
import { DATA_MANIFEST_URLS, SUPPORTED_SCHEMA, UPDATE_CHECK_EVERY_MS } from '#lib/config.ts';
import { isManifest, type Manifest } from './manifest';
import { all, openDatabase } from './sqlite';
import { sha256 } from './sha256';
import { lastChecked, loadInstalled, markChecked, saveInstalled } from './storage';

export type Status = 'starting' | 'ready' | 'downloading' | 'missing' | 'error';
export type UpdateState =
	| { state: 'idle' }
	| { state: 'checking' }
	| { state: 'downloading'; received: number; total: number }
	| { state: 'current'; at: number }
	| { state: 'updated'; at: number; from: string | null }
	| { state: 'offline' }
	| { state: 'app-too-old'; version: string }
	| { state: 'failed'; message: string };

async function readWithProgress(res: Response, onProgress: (n: number) => void): Promise<Uint8Array> {
	if (!res.body) return new Uint8Array(await res.arrayBuffer());
	const reader = res.body.getReader();
	const chunks: Uint8Array[] = [];
	let received = 0;
	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;
		chunks.push(value);
		received += value.length;
		onProgress(received);
	}
	const out = new Uint8Array(received);
	let off = 0;
	for (const c of chunks) {
		out.set(c, off);
		off += c.length;
	}
	return out;
}

async function gunzip(bytes: Uint8Array): Promise<Uint8Array> {
	const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream('gzip'));
	return new Uint8Array(await new Response(stream).arrayBuffer());
}

class Timetable {
	status = $state<Status>('starting');
	manifest = $state<Manifest | null>(null);
	update = $state<UpdateState>({ state: 'idle' });
	/** Bumped whenever a different database is swapped in; queries read it
	 *  so that derived views recompute. */
	revision = $state(0);
	error = $state<string | null>(null);
	db: Database | null = null;

	private started = false;

	async start(): Promise<void> {
		if (this.started) return;
		this.started = true;
		try {
			const installed = await loadInstalled();
			if (installed) {
				await this.use(installed.manifest, installed.bytes);
			}
		} catch (e) {
			console.warn('stored timetable unreadable, will download again', e);
		}
		if (!this.db) {
			this.status = 'downloading';
			await this.check(true);
			if (!this.db) this.status = navigator.onLine ? 'error' : 'missing';
			return;
		}
		if (Date.now() - lastChecked() > UPDATE_CHECK_EVERY_MS) void this.check();
		addEventListener('online', () => {
			if (Date.now() - lastChecked() > UPDATE_CHECK_EVERY_MS) void this.check();
		});
	}

	/** Look for a newer release; download and install it if there is one. */
	async check(force = false): Promise<void> {
		if (this.update.state === 'checking' || this.update.state === 'downloading') return;
		if (!navigator.onLine && !force) {
			this.update = { state: 'offline' };
			return;
		}
		this.update = { state: 'checking' };
		try {
			let res: Response | undefined;
			let manifestUrl = DATA_MANIFEST_URLS[0];
			for (const url of DATA_MANIFEST_URLS) {
				manifestUrl = url;
				res = await fetch(url, { cache: 'no-store' });
				if (res.status !== 404) break;
			}
			if (!res?.ok) throw new Error(`manifest: HTTP ${res?.status}`);
			const manifest: unknown = await res.json();
			if (!isManifest(manifest)) throw new Error('manifest is not in the expected format');
			markChecked();
			if (!SUPPORTED_SCHEMA.includes(manifest.schema_version)) {
				this.update = { state: 'app-too-old', version: manifest.version };
				return;
			}
			if (this.manifest?.version === manifest.version && this.db) {
				this.update = { state: 'current', at: Date.now() };
				return;
			}
			// Relative to where the manifest really came from (after redirects).
			const dbUrl = new URL(manifest.db.url, res.url || new URL(manifestUrl, location.href));
			this.update = { state: 'downloading', received: 0, total: manifest.db.size };
			const dbRes = await fetch(dbUrl, { cache: 'no-cache' });
			if (!dbRes.ok) throw new Error(`timetable download: HTTP ${dbRes.status}`);
			const packed = await readWithProgress(dbRes, (received) => {
				this.update = { state: 'downloading', received, total: manifest.db.size };
			});
			if ((await sha256(packed)) !== manifest.db.sha256) throw new Error('download is corrupt (checksum mismatch)');
			const bytes = manifest.db.encoding === 'gzip' ? await gunzip(packed) : packed;
			if ((await sha256(bytes)) !== manifest.db.raw_sha256) throw new Error('timetable is corrupt (checksum mismatch)');
			const from = this.manifest?.version ?? null;
			await this.use(manifest, bytes);
			await saveInstalled(manifest, bytes);
			this.update = { state: 'updated', at: Date.now(), from };
		} catch (e) {
			const offline = !navigator.onLine || e instanceof TypeError;
			this.update = offline ? { state: 'offline' } : { state: 'failed', message: (e as Error).message };
			this.error = (e as Error).message;
		}
	}

	private async use(manifest: Manifest, bytes: Uint8Array): Promise<void> {
		const db = await openDatabase(bytes);
		// Prove it is a timetable this app can read before letting go of the old one.
		const meta = all<{ value: string }>(db, "SELECT value FROM meta WHERE key = 'schema_version'");
		if (!meta.length || !SUPPORTED_SCHEMA.includes(Number(meta[0].value))) {
			db.close();
			throw new Error('timetable schema not supported by this version of the app');
		}
		const old = this.db;
		this.db = db;
		this.manifest = manifest;
		this.revision += 1;
		this.status = 'ready';
		this.error = null;
		old?.close();
	}
}

export const timetable = new Timetable();
