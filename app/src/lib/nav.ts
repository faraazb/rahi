/** Links between screens. `resolve` adds the deploy base path (GitHub
 *  Pages serves the app from /<repo>). */
import { resolve } from '$app/paths';

function qs(params: Record<string, string | number | null | undefined>): string {
	const p = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') p.set(k, String(v));
	const s = p.toString();
	return s ? `?${s}` : '';
}

export const href = {
	home: () => resolve('/'),
	trains: (from?: string | null, to?: string | null) => resolve('/trains') + qs({ from, to }),
	train: (id: number, from?: string | null, to?: string | null) =>
		resolve('/train/[id]', { id: String(id) }) + qs({ from, to }),
	station: (code: string, dir?: 'up' | 'down') => resolve('/station/[code]', { code }) + qs({ dir }),
	settings: () => resolve('/settings'),
	offline: () => resolve('/settings/offline'),
	savedStations: () => resolve('/settings/stations')
};
