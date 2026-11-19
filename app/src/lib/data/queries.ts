/** Timetable questions the screens ask, answered from the SQLite release
 *  (schema: pipeline/src/mumbailocal/build_db.py, versions 2 and 3).
 *
 *  Version 3 adds stop_time.arr_min (arrival where the source gives one apart
 *  from the departure), stop_time.pos (stations along the train's route), so
 *  fast trains are told apart on branching and looping routes too, and
 *  line_station.ord (the trunk, then each branch, for station lists). A v2
 *  database still works: queries fall back to line positions.
 *
 *  Times are minutes since midnight of the service day (03:00-03:00), so a
 *  00:30 departure is 1470. Queries fetch a whole service day once per
 *  (database, question, weekday) and cache it; the clock ticking only
 *  filters those rows, it never re-runs SQL.
 *
 *  Platforms: an optional `platform` table (train_id, seq) -> platform and
 *  door side. Only local builds carry it (pipeline/src/mumbailocal/platforms.py,
 *  from the Yatri app); public releases do not, so every query works without
 *  it and platform fields are then null.
 *
 *  Rake links: an optional `rake_next` table (train_id -> next_train_id),
 *  also local-only (pipeline/src/mumbailocal/rakes.py). Without it trips
 *  simply have no return boarding. */
import type { Database } from 'sql.js';
import { all, one } from './sqlite';
import type { ServiceNow } from '#lib/time.ts';

/** Which side the doors open, relative to the direction of travel. */
export type DoorSide = 'LEFT' | 'RIGHT' | 'BOTH';

export interface Station {
	id: number;
	code: string;
	name: string;
	/** Line codes serving the station, e.g. ['WR']. */
	lines: string[];
	/** Stations from each line's root (Churchgate, CSMT: seq 1); equal on parallel branches. */
	seq: Record<string, number>;
}

export interface Trip {
	trainId: number;
	number: string;
	line: string;
	/** 1 = up (towards the city terminus), 2 = down. */
	direction: number;
	dep: number;
	arr: number;
	minutes: number;
	/** Skips at least one station between your two stations. */
	fast: boolean;
	/** Air-conditioned on this day (some AC rakes run ordinary at weekends). */
	ac: boolean;
	cars: number | null;
	dest: string;
	destCode: string;
	days: string;
	notOnHolidays: boolean;
	operator: string | null;
	/** Platform at the departure station: "4", or "1,2" for one of these. */
	pf: string | null;
	/** Set on trips from the next service day, appended after the last train. */
	tomorrow?: boolean;
	/** Board earlier and stay on (local builds with rake links only). */
	ret?: ReturnBoarding | null;
}

/** Catching your train earlier, on its way into the terminus where it turns:
 *  board this train at your station and stay on. */
export interface ReturnBoarding {
	trainId: number;
	/** Departure from your station, on the trip's own service day. */
	dep: number;
	pf: string | null;
	/** Where it turns. */
	terminus: string;
}

export interface Departure {
	trainId: number;
	number: string;
	time: number;
	fast: boolean;
	ac: boolean;
	cars: number | null;
	dest: string;
	destCode: string;
	days: string;
	notOnHolidays: boolean;
	operator: string | null;
	pf: string | null;
	tomorrow?: boolean;
}

export interface TrainStop {
	seq: number;
	time: number;
	stationId: number;
	code: string;
	name: string;
	/** Position on the train's line; null for a terminal off the line (CSMT). */
	lineSeq: number | null;
	pf: string | null;
	/** Shown only where the source agrees with itself for this platform. */
	doors: DoorSide | null;
	/** Arrival, where the timetable gives one apart from `time` (the departure). */
	arr: number | null;
	/** Stations along the train's route from its first stop (schema 3), else null. */
	pos: number | null;
}

export interface TrainDetail {
	id: number;
	number: string;
	line: string;
	lineName: string;
	direction: number;
	fast: boolean;
	ac: boolean;
	acWeekdaysOnly: boolean;
	ladies: boolean;
	cars: number | null;
	days: string;
	notOnHolidays: boolean;
	operator: string | null;
	origin: string;
	dest: string;
	destTimeMissing: boolean;
	notes: string | null;
	stops: TrainStop[];
}

// ---------------------------------------------------------------- caching

let cacheDb: Database | null = null;
const cache = new Map<string, unknown>();

function cached<T>(db: Database, key: string, compute: () => T): T {
	if (db !== cacheDb) {
		cache.clear();
		cacheDb = db;
	}
	if (!cache.has(key)) cache.set(key, compute());
	return cache.get(key) as T;
}

// ---------------------------------------------------------------- platforms

/** Whether this database carries the (local-only) platform layer. */
export function hasPlatforms(db: Database): boolean {
	return cached(db, 'hasPlatforms', () => !!one(db, "SELECT 1 AS x FROM sqlite_master WHERE type = 'table' AND name = 'platform'"));
}

/** SQL pieces that add `pf` (and `doors`) for the stop aliased `stop`. */
function platformSql(db: Database, stop: string): { cols: string; join: string } {
	return hasPlatforms(db)
		? {
				cols: 'p.platform AS pf, p.door_side AS doors',
				join: `LEFT JOIN platform p ON p.train_id = ${stop}.train_id AND p.seq = ${stop}.seq`
			}
		: { cols: 'NULL AS pf, NULL AS doors', join: '' };
}

/** "1,2" -> "1/2" for display. */
export function pfLabel(pf: string | null | undefined): string | null {
	return pf ? pf.replaceAll(',', '/') : null;
}

export function doorsLabel(d: DoorSide | null | undefined): string | null {
	if (d === 'LEFT') return 'doors on left';
	if (d === 'RIGHT') return 'doors on right';
	if (d === 'BOTH') return 'doors on both sides';
	return null;
}

// ---------------------------------------------------------------- rake links

/** next train id -> the trip its rake works just before, when the database has rake links. */
function rakePrev(db: Database): Map<number, number> | null {
	return cached(db, 'rakePrev', () => {
		if (!one(db, "SELECT 1 AS x FROM sqlite_master WHERE type = 'table' AND name = 'rake_next'")) return null;
		const m = new Map<number, number>();
		for (const r of all<{ a: number; b: number }>(db, 'SELECT train_id AS a, next_train_id AS b FROM rake_next')) m.set(r.b, r.a);
		return m;
	});
}

/** Where to board `trip`'s train earlier at `from`, while it is still heading
 *  into the terminus where it turns into `trip`. Null when the database has no
 *  rake links, the earlier trip does not call at `from` (or ends there), or it
 *  does not run that day. `dow` is the trip's own service day. */
export function returnBoarding(db: Database, trip: Trip, from: Station, dow: number): ReturnBoarding | null {
	const prev = rakePrev(db)?.get(trip.trainId);
	if (prev === undefined) return null;
	return cached(db, `ret:${trip.trainId}:${from.id}:${dow}`, () => {
		const p = platformSql(db, 'a');
		const r = one<{ dep: number; days: string; last: number; seq: number; terminus: string | null; pf: string | null }>(
			db,
			`SELECT a.time_min AS dep, sv.days, a.seq,
			        (SELECT MAX(x.seq) FROM stop_time x WHERE x.train_id = a.train_id) AS last,
			        ds.name AS terminus, ${p.cols}
			   FROM stop_time a
			   JOIN train t ON t.id = a.train_id
			   JOIN service sv ON sv.id = t.service_id
			   LEFT JOIN station ds ON ds.id = t.dest_station_id
			   ${p.join}
			  WHERE a.train_id = ? AND a.station_id = ?`,
			[prev, from.id]
		);
		if (!r || r.seq >= r.last || r.days[dow] !== '1') return null;
		// The rake comes back through your station, so it must pass you first.
		if (r.dep >= trip.dep - (trip.tomorrow ? 1440 : 0)) return null;
		return { trainId: prev, dep: r.dep, pf: r.pf, terminus: r.terminus ?? '' };
	});
}

/** `trips` with `ret` set where a return boarding exists (`now.dow` is today). */
export function withReturns<T extends Trip>(db: Database, trips: T[], from: Station, dow: number): (T & { ret: ReturnBoarding | null })[] {
	if (!rakePrev(db)) return trips.map((t) => ({ ...t, ret: null }));
	return trips.map((t) => {
		const ret = returnBoarding(db, t, from, t.tomorrow ? (dow + 1) % 7 : dow);
		return { ...t, ret: ret && t.tomorrow ? { ...ret, dep: ret.dep + 1440 } : ret };
	});
}

// ---------------------------------------------------------------- schema 3

/** Whether stop_time carries arr_min and pos (schema 3). */
export function hasRoutePositions(db: Database): boolean {
	return cached(db, 'hasRoutePositions', () =>
		all<{ name: string }>(db, 'PRAGMA table_info(stop_time)').some((c) => c.name === 'pos')
	);
}

/** SQL for the arrival time and route position of the stop aliased `stop`. */
function stopSql(db: Database, stop: string): { arr: string; pos: string } {
	return hasRoutePositions(db)
		? { arr: `COALESCE(${stop}.arr_min, ${stop}.time_min)`, pos: `${stop}.pos` }
		: { arr: `${stop}.time_min`, pos: 'NULL' };
}

/** Fast between two stops: it calls at fewer stops than there are stations
 *  between them. `stopsApart` is the difference in stop sequence. */
export function skipsStations(stopsApart: number, posA: number | null, posB: number | null, lineSeqA?: number, lineSeqB?: number): boolean {
	if (posA !== null && posB !== null) return stopsApart < posB - posA;
	// Schema 2: line positions, exact on unbranched runs.
	if (lineSeqA === undefined || lineSeqB === undefined) return false;
	return stopsApart < Math.abs(lineSeqB - lineSeqA);
}

// ---------------------------------------------------------------- stations

export function stations(db: Database): Station[] {
	return cached(db, 'stations', () => {
		const rows = all<{ id: number; code: string; name: string; line: string; seq: number }>(
			db,
			`SELECT s.id, s.code, s.name, l.code AS line, ls.seq
			   FROM line_station ls
			   JOIN station s ON s.id = ls.station_id
			   JOIN line l ON l.id = ls.line_id
			  ORDER BY l.id, ${hasRoutePositions(db) ? 'ls.ord' : 'ls.seq'}`
		);
		const byId = new Map<number, Station>();
		for (const r of rows) {
			const st = byId.get(r.id) ?? { id: r.id, code: r.code, name: r.name, lines: [], seq: {} };
			st.lines.push(r.line);
			st.seq[r.line] = r.seq;
			byId.set(r.id, st);
		}
		return [...byId.values()];
	});
}

export function stationByCode(db: Database, code: string): Station | null {
	return stations(db).find((s) => s.code === code) ?? null;
}

export function lines(db: Database): { code: string; name: string }[] {
	return cached(db, 'lines', () => all(db, 'SELECT code, name FROM line ORDER BY id'));
}

// ---------------------------------------------------------------- search

/** Stations matching what was typed, best first (design: exact code, name
 *  prefix, code prefix, word prefix). */
export function searchStations(db: Database, q: string, exclude?: string | null, limit = 6): Station[] {
	const ql = q.trim().toLowerCase();
	if (!ql) return [];
	const qu = ql.toUpperCase();
	const score = (st: Station): number => {
		const name = st.name.toLowerCase();
		if (st.code === qu) return 0;
		if (name.startsWith(ql)) return 1;
		if (st.code.startsWith(qu)) return 2;
		if (name.split(/[\s-]+/).some((w) => w.startsWith(ql))) return 3;
		if (name.replace(/[^a-z]/g, '').startsWith(ql.replace(/[^a-z]/g, ''))) return 4;
		return 9;
	};
	return stations(db)
		.filter((st) => st.code !== exclude)
		.map((st) => [score(st), st] as const)
		.filter(([s]) => s < 9)
		.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name))
		.slice(0, limit)
		.map(([, st]) => st);
}

// ---------------------------------------------------------------- trips

/** Every trip of the service day from one station to another. */
export function tripsOn(db: Database, from: Station, to: Station, dow: number): Trip[] {
	return cached(db, `trips:${from.id}:${to.id}:${dow}`, () => {
		const weekend = dow >= 5;
		const p = platformSql(db, 'a');
		const sa = stopSql(db, 'a');
		const sb = stopSql(db, 'b');
		const rows = all<{
			id: number; number: string; direction: number; is_ac: number; ac_weekdays_only: number;
			cars: number | null; operator: string | null; line: string; days: string; not_on_holidays: number;
			dep: number; arr: number; aseq: number; bseq: number; apos: number | null; bpos: number | null;
			dest: string | null; dest_code: string | null; pf: string | null;
		}>(
			db,
			`SELECT t.id, t.number, t.direction, t.is_ac, t.ac_weekdays_only, t.cars, t.operator,
			        l.code AS line, sv.days, sv.not_on_holidays,
			        a.time_min AS dep, ${sb.arr} AS arr, a.seq AS aseq, b.seq AS bseq,
			        ${sa.pos} AS apos, ${sb.pos} AS bpos,
			        ds.name AS dest, ds.code AS dest_code, ${p.cols}
			   FROM stop_time a
			   JOIN stop_time b ON b.train_id = a.train_id AND b.seq > a.seq AND b.station_id = ?
			   JOIN train t ON t.id = a.train_id
			   JOIN line l ON l.id = t.line_id
			   JOIN service sv ON sv.id = t.service_id
			   LEFT JOIN station ds ON ds.id = t.dest_station_id
			   ${p.join}
			  WHERE a.station_id = ? AND substr(sv.days, ?, 1) = '1'
			  ORDER BY a.time_min, t.number`,
			[to.id, from.id, dow + 1]
		);
		return rows.map((r) => ({
			trainId: r.id,
			number: r.number,
			line: r.line,
			direction: r.direction,
			dep: r.dep,
			arr: r.arr,
			minutes: r.arr - r.dep,
			fast: skipsStations(r.bseq - r.aseq, r.apos, r.bpos, from.seq[r.line], to.seq[r.line]),
			ac: !!r.is_ac && !(r.ac_weekdays_only && weekend),
			cars: r.cars,
			dest: r.dest ?? to.name,
			destCode: r.dest_code ?? to.code,
			days: r.days,
			notOnHolidays: !!r.not_on_holidays,
			operator: r.operator,
			pf: r.pf
		}));
	});
}

/** The next trips from `now`, running into tomorrow's first trains if the
 *  day's service is nearly over. */
export function upcomingTrips(db: Database, from: Station, to: Station, now: ServiceNow, limit: number): Trip[] {
	const today = tripsOn(db, from, to, now.dow).filter((t) => t.dep >= now.minute);
	if (today.length >= limit) return today.slice(0, limit);
	const tomorrow = tripsOn(db, from, to, (now.dow + 1) % 7).map((t) => ({
		...t,
		dep: t.dep + 1440,
		arr: t.arr + 1440,
		tomorrow: true
	}));
	return [...today, ...tomorrow].slice(0, limit);
}

// ---------------------------------------------------------------- station board

export function departuresOn(db: Database, station: Station, line: string, direction: number, dow: number): Departure[] {
	return cached(db, `deps:${station.id}:${line}:${direction}:${dow}`, () => {
		const weekend = dow >= 5;
		const p = platformSql(db, 'a');
		const rows = all<{
			id: number; number: string; is_fast: number | null; is_ac: number; ac_weekdays_only: number;
			cars: number | null; operator: string | null; days: string; not_on_holidays: number;
			time: number; dest: string | null; dest_code: string | null; pf: string | null;
		}>(
			db,
			`SELECT t.id, t.number, t.is_fast, t.is_ac, t.ac_weekdays_only, t.cars, t.operator,
			        sv.days, sv.not_on_holidays, a.time_min AS time, ds.name AS dest, ds.code AS dest_code, ${p.cols}
			   FROM stop_time a
			   JOIN train t ON t.id = a.train_id
			   JOIN line l ON l.id = t.line_id
			   JOIN service sv ON sv.id = t.service_id
			   LEFT JOIN station ds ON ds.id = t.dest_station_id
			   ${p.join}
			  WHERE a.station_id = ? AND l.code = ? AND t.direction = ? AND substr(sv.days, ?, 1) = '1'
			    AND (a.seq < (SELECT MAX(x.seq) FROM stop_time x WHERE x.train_id = t.id)
			         OR t.dest_time_missing = 1)
			  ORDER BY a.time_min, t.number`,
			[station.id, line, direction, dow + 1]
		);
		return rows
			.filter((r) => r.dest_code !== station.code)
			.map((r) => ({
				trainId: r.id,
				number: r.number,
				time: r.time,
				fast: !!r.is_fast,
				ac: !!r.is_ac && !(r.ac_weekdays_only && weekend),
				cars: r.cars,
				dest: r.dest ?? '—',
				destCode: r.dest_code ?? '',
				days: r.days,
				notOnHolidays: !!r.not_on_holidays,
				operator: r.operator,
				pf: r.pf
			}));
	});
}

export function upcomingDepartures(db: Database, station: Station, line: string, direction: number, now: ServiceNow, limit: number): Departure[] {
	const today = departuresOn(db, station, line, direction, now.dow).filter((d) => d.time >= now.minute);
	if (today.length >= limit) return today.slice(0, limit);
	const tomorrow = departuresOn(db, station, line, direction, (now.dow + 1) % 7).map((d) => ({
		...d,
		time: d.time + 1440,
		tomorrow: true
	}));
	return [...today, ...tomorrow].slice(0, limit);
}

/** Where trains leaving `station` in one direction go, most frequent first:
 *  names a direction on lines whose trains have no single end that way. */
export function directionDestinations(db: Database, station: Station, line: string, direction: number): string[] {
	return cached(db, `dirdest:${station.id}:${line}:${direction}`, () =>
		all<{ name: string }>(
			db,
			`SELECT ds.name, COUNT(*) AS n
			   FROM stop_time a
			   JOIN train t ON t.id = a.train_id
			   JOIN line l ON l.id = t.line_id
			   JOIN station ds ON ds.id = t.dest_station_id
			  WHERE a.station_id = ? AND l.code = ? AND t.direction = ? AND ds.id <> a.station_id
			  GROUP BY ds.id ORDER BY n DESC, ds.name`,
			[station.id, line, direction]
		).map((r) => r.name)
	);
}

export function trainsCalling(db: Database, station: Station, dow: number): number {
	return cached(db, `calling:${station.id}:${dow}`, () =>
		one<{ n: number }>(
			db,
			`SELECT COUNT(DISTINCT st.train_id) AS n FROM stop_time st
			   JOIN train t ON t.id = st.train_id JOIN service sv ON sv.id = t.service_id
			  WHERE st.station_id = ? AND substr(sv.days, ?, 1) = '1'`,
			[station.id, dow + 1]
		)?.n ?? 0
	);
}

// ---------------------------------------------------------------- one train

export function train(db: Database, id: number): TrainDetail | null {
	return cached(db, `train:${id}`, () => {
		const t = one<{
			id: number; number: string; line: string; line_name: string; line_id: number; direction: number;
			is_fast: number | null; is_ac: number; ac_weekdays_only: number; ladies_special: number;
			cars: number | null; days: string; not_on_holidays: number; operator: string | null;
			origin: string | null; dest: string | null; dest_time_missing: number; notes: string | null;
		}>(
			db,
			`SELECT t.id, t.number, l.code AS line, l.name AS line_name, l.id AS line_id, t.direction,
			        t.is_fast, t.is_ac, t.ac_weekdays_only, t.ladies_special, t.cars, sv.days, sv.not_on_holidays,
			        t.operator, o.name AS origin, d.name AS dest, t.dest_time_missing, t.notes
			   FROM train t
			   JOIN line l ON l.id = t.line_id
			   JOIN service sv ON sv.id = t.service_id
			   LEFT JOIN station o ON o.id = t.origin_station_id
			   LEFT JOIN station d ON d.id = t.dest_station_id
			  WHERE t.id = ?`,
			[id]
		);
		if (!t) return null;
		const p = platformSql(db, 'st');
		const ss = stopSql(db, 'st');
		const stops = all<{
			seq: number; time: number; arr: number; pos: number | null; id: number; code: string; name: string;
			line_seq: number | null; pf: string | null; doors: DoorSide | null;
		}>(
			db,
			`SELECT st.seq, st.time_min AS time, ${ss.arr} AS arr, ${ss.pos} AS pos,
			        s.id, s.code, s.name, ls.seq AS line_seq, ${p.cols}
			   FROM stop_time st
			   JOIN station s ON s.id = st.station_id
			   LEFT JOIN line_station ls ON ls.station_id = s.id AND ls.line_id = ?
			   ${p.join}
			  WHERE st.train_id = ?
			  ORDER BY st.seq`,
			[t.line_id, id]
		).map((s) => ({
			seq: s.seq, time: s.time, stationId: s.id, code: s.code, name: s.name, lineSeq: s.line_seq,
			pf: s.pf, doors: s.doors, arr: s.arr !== s.time ? s.arr : null, pos: s.pos
		}));
		return {
			id: t.id,
			number: t.number,
			line: t.line,
			lineName: t.line_name,
			direction: t.direction,
			fast: !!t.is_fast,
			ac: !!t.is_ac,
			acWeekdaysOnly: !!t.ac_weekdays_only,
			ladies: !!t.ladies_special,
			cars: t.cars,
			days: t.days,
			notOnHolidays: !!t.not_on_holidays,
			operator: t.operator,
			origin: t.origin ?? stops[0]?.name ?? '',
			dest: t.dest ?? stops.at(-1)?.name ?? '',
			destTimeMissing: !!t.dest_time_missing,
			notes: t.notes,
			stops
		};
	});
}
