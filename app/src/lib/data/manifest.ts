/** The release manifest written by `mumbailocal release` (pipeline). */
export interface Manifest {
	format: 1;
	version: string;
	schema_version: number;
	published_at: string;
	built_at: string | null;
	lines: {
		code: string;
		name: string;
		/** w.e.f. printed on the railway's timetable, when it prints one. */
		effective_from: string | null;
		/** When the source files were taken (newer releases only). */
		as_of?: string | null;
		sources: Record<string, string>;
	}[];
	counts: { trains: number; stations: number };
	/** Optional tables inside the database, e.g. platforms (local builds only). */
	layers?: Record<string, { source: string | null; local_only: boolean }>;
	/** A local build that must never be published. */
	local?: boolean;
	db: {
		url: string;
		encoding: 'gzip' | 'identity';
		size: number;
		sha256: string;
		raw_size: number;
		raw_sha256: string;
	};
}

export function isManifest(x: unknown): x is Manifest {
	const m = x as Manifest;
	return (
		!!m &&
		m.format === 1 &&
		typeof m.version === 'string' &&
		typeof m.schema_version === 'number' &&
		!!m.db &&
		typeof m.db.url === 'string' &&
		/^[0-9a-f]{64}$/.test(m.db.sha256)
	);
}
