/** What the rider keeps: pinned routes, saved stations, recent picks, and
 *  which routes they look up at which hour (for "usual at this hour").
 *  Stored on the device only; nothing leaves it. Stations are kept by code. */
const KEY = 'rahi.saved';

export interface Route {
	from: string;
	to: string;
}

interface Stored {
	pinned: Route[];
	stations: string[];
	recent: string[];
	/** "FROM>TO" -> lookups per hour of day (24 counters). */
	usage: Record<string, number[]>;
	last: Route | null;
}

const EMPTY: Stored = { pinned: [], stations: [], recent: [], usage: {}, last: null };
const key = (r: Route) => `${r.from}>${r.to}`;

class Saved {
	pinned = $state<Route[]>([]);
	stations = $state<string[]>([]);
	recent = $state<string[]>([]);
	usage = $state<Record<string, number[]>>({});
	last = $state<Route | null>(null);

	load(): void {
		let s: Stored = EMPTY;
		try {
			s = { ...EMPTY, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') };
		} catch {
			/* start empty */
		}
		this.pinned = s.pinned;
		this.stations = s.stations;
		this.recent = s.recent;
		this.usage = s.usage;
		this.last = s.last;
	}

	persist(): void {
		const s: Stored = {
			pinned: this.pinned,
			stations: this.stations,
			recent: this.recent,
			usage: this.usage,
			last: this.last
		};
		try {
			localStorage.setItem(KEY, JSON.stringify(s));
		} catch {
			/* not persisted in private mode */
		}
	}

	isPinned(r: Route): boolean {
		return this.pinned.some((p) => key(p) === key(r));
	}

	togglePin(r: Route): void {
		this.pinned = this.isPinned(r) ? this.pinned.filter((p) => key(p) !== key(r)) : [...this.pinned, r];
		this.persist();
	}

	isSaved(code: string): boolean {
		return this.stations.includes(code);
	}

	toggleStation(code: string): void {
		this.stations = this.isSaved(code) ? this.stations.filter((c) => c !== code) : [...this.stations, code];
		this.persist();
	}

	picked(code: string): void {
		this.recent = [code, ...this.recent.filter((c) => c !== code)].slice(0, 6);
		this.persist();
	}

	/** A route was looked up at `hour` (0-23, Mumbai time). */
	used(r: Route, hour: number): void {
		const counts = [...(this.usage[key(r)] ?? Array(24).fill(0))];
		counts[hour] += 1;
		this.usage = { ...this.usage, [key(r)]: counts };
		this.last = r;
		this.persist();
	}

	/** The route usually looked up around this hour, if the pattern is clear:
	 *  at least 3 lookups within an hour either side. */
	usualAt(hour: number, among: Route[]): Route | null {
		let best: [number, Route | null] = [0, null];
		for (const r of among) {
			const c = this.usage[key(r)];
			if (!c) continue;
			const n = c[(hour + 23) % 24] + c[hour] + c[(hour + 1) % 24];
			if (n > best[0]) best = [n, r];
		}
		return best[0] >= 3 ? best[1] : null;
	}
}

export const saved = new Saved();
export const routeKey = key;
