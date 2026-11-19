/** Journeys with changes, for station pairs no single train serves.
 *
 *  Round-based search over the whole service day (RAPTOR, scanning every
 *  trip each round): round k finds the earliest arrival at every station
 *  using k trains, so the answer is exact for any number of changes up to
 *  MAX_TRAINS - 1, and the rounds give the trade-off between arriving
 *  earlier and changing less.
 *
 *  Everything comes from the timetable except two rules of our own, since
 *  no official source publishes them:
 *  - CHANGE_MIN: the least time to leave one train and catch another at the
 *    same station.
 *  - WALKS: stations the timetable keeps apart that riders change between on
 *    foot (Western's and Central's Dadar), with the time the walk takes.
 *
 *  Self-contained (no Vite imports) so it can be checked against a real
 *  database from Node. */
import type { Database } from 'sql.js';

export const CHANGE_MIN = 3;
/** Station code pairs joined on foot, and the minutes to change between them. */
export const WALKS: [string, string, number][] = [['DDR', 'DR', 6]];
export const MAX_TRAINS = 4;

export interface Leg {
	trainId: number;
	number: string;
	line: string;
	fast: boolean;
	ac: boolean;
	cars: number | null;
	/** Where the train is going (its last stop). */
	towards: string;
	fromCode: string;
	fromName: string;
	toCode: string;
	toName: string;
	dep: number;
	arr: number;
	pfFrom: string | null;
	pfTo: string | null;
}

export interface Change {
	/** Minutes between arriving and the next train leaving. */
	minutes: number;
	/** Within a minute of the least time we allow. */
	tight: boolean;
	/** Set when the change means walking to another station (Dadar W to C). */
	walk: { fromName: string; toName: string; fromLine: string; toLine: string } | null;
}

export interface Journey {
	legs: Leg[];
	/** changes[i] sits between legs[i] and legs[i + 1]. */
	changes: Change[];
	/** Minutes on foot before the first train (from Dadar W to C, say), or after the last; 0 if none. */
	walkStart: number;
	walkEnd: number;
	/** When to set off and when you get there, walks included. */
	dep: number;
	arr: number;
	minutes: number;
	tomorrow?: boolean;
}

// ---------------------------------------------------------------- network

interface Stop {
	station: number;
	dep: number;
	arr: number;
	pos: number | null;
	pf: string | null;
}

interface TripRow {
	id: number;
	number: string;
	line: string;
	ac: boolean;
	cars: number | null;
	dest: number;
	stops: Stop[];
}

interface Network {
	trips: TripRow[];
	code: Map<number, string>;
	name: Map<number, string>;
	byCode: Map<string, number>;
	/** line code -> station id -> position on the line, for databases without stop_time.pos. */
	lineSeq: Map<string, Map<number, number>>;
	walks: Map<number, { to: number; minutes: number }[]>;
}

function rows<T>(db: Database, sql: string, params: (string | number)[] = []): T[] {
	const stmt = db.prepare(sql);
	try {
		stmt.bind(params);
		const out: T[] = [];
		while (stmt.step()) out.push(stmt.getAsObject() as T);
		return out;
	} finally {
		stmt.free();
	}
}

function hasColumn(db: Database, table: string, col: string): boolean {
	return rows<{ name: string }>(db, `PRAGMA table_info(${table})`).some((c) => c.name === col);
}

function hasTable(db: Database, name: string): boolean {
	return rows(db, "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", [name]).length > 0;
}

let netDb: Database | null = null;
const nets = new Map<number, Network>();

/** Every trip running on weekday `dow` (Monday 0), loaded once per database and day. */
function network(db: Database, dow: number): Network {
	if (db !== netDb) {
		nets.clear();
		netDb = db;
	}
	const hit = nets.get(dow);
	if (hit) return hit;

	const v3 = hasColumn(db, 'stop_time', 'pos');
	const pf = hasTable(db, 'platform');
	const weekend = dow >= 5;
	const stopRows = rows<{
		id: number; number: string; line: string; is_ac: number; ac_weekdays_only: number; cars: number | null;
		dest: number | null; station: number; dep: number; arr: number; pos: number | null; pf: string | null;
	}>(
		db,
		`SELECT t.id, t.number, l.code AS line, t.is_ac, t.ac_weekdays_only, t.cars, t.dest_station_id AS dest,
		        st.station_id AS station, st.time_min AS dep,
		        ${v3 ? 'COALESCE(st.arr_min, st.time_min)' : 'st.time_min'} AS arr,
		        ${v3 ? 'st.pos' : 'NULL'} AS pos, ${pf ? 'p.platform' : 'NULL'} AS pf
		   FROM stop_time st
		   JOIN train t ON t.id = st.train_id
		   JOIN line l ON l.id = t.line_id
		   JOIN service sv ON sv.id = t.service_id
		   ${pf ? 'LEFT JOIN platform p ON p.train_id = st.train_id AND p.seq = st.seq' : ''}
		  WHERE substr(sv.days, ?, 1) = '1'
		  ORDER BY t.id, st.seq`,
		[dow + 1]
	);
	const trips: TripRow[] = [];
	for (const r of stopRows) {
		let t = trips.at(-1);
		if (!t || t.id !== r.id) {
			t = { id: r.id, number: r.number, line: r.line, ac: !!r.is_ac && !(r.ac_weekdays_only && weekend), cars: r.cars, dest: r.dest ?? r.station, stops: [] };
			trips.push(t);
		}
		t.stops.push({ station: r.station, dep: r.dep, arr: r.arr, pos: r.pos, pf: r.pf });
	}
	for (const t of trips) if (t.dest === t.stops[0].station || !t.dest) t.dest = t.stops.at(-1)!.station;

	const code = new Map<number, string>();
	const name = new Map<number, string>();
	const byCode = new Map<string, number>();
	for (const s of rows<{ id: number; code: string; name: string }>(db, 'SELECT id, code, name FROM station')) {
		code.set(s.id, s.code);
		name.set(s.id, s.name);
		byCode.set(s.code, s.id);
	}
	const lineSeq = new Map<string, Map<number, number>>();
	for (const r of rows<{ line: string; station: number; seq: number }>(
		db,
		'SELECT l.code AS line, ls.station_id AS station, ls.seq FROM line_station ls JOIN line l ON l.id = ls.line_id'
	)) {
		if (!lineSeq.has(r.line)) lineSeq.set(r.line, new Map());
		lineSeq.get(r.line)!.set(r.station, r.seq);
	}
	const walks = new Map<number, { to: number; minutes: number }[]>();
	for (const [a, b, minutes] of WALKS) {
		const ia = byCode.get(a);
		const ib = byCode.get(b);
		if (ia === undefined || ib === undefined) continue;
		walks.set(ia, [...(walks.get(ia) ?? []), { to: ib, minutes }]);
		walks.set(ib, [...(walks.get(ib) ?? []), { to: ia, minutes }]);
	}
	const net = { trips, code, name, byCode, lineSeq, walks };
	nets.set(dow, net);
	return net;
}

// ---------------------------------------------------------------- search

/** How a station was reached in a round. */
type Label =
	| { kind: 'origin' }
	| { kind: 'ride'; trip: TripRow; board: number; alight: number; prev: number }
	| { kind: 'walk'; from: number; minutes: number };

interface Round {
	arr: Map<number, number>;
	/** When a train can be caught from here: arrival plus the change time (a walk already includes it). */
	ready: Map<number, number>;
	label: Map<number, Label>;
}

/** Earliest arrival using k trains, for each k that improves on fewer trains. */
function search(net: Network, origin: number, target: number, t0: number): Journey[] {
	const best = new Map<number, number>([[origin, t0]]);
	const rounds: Round[] = [{ arr: new Map([[origin, t0]]), ready: new Map([[origin, t0]]), label: new Map([[origin, { kind: 'origin' }]]) }];
	walkFrom(net, rounds[0], best, [origin], target);

	for (let k = 1; k <= MAX_TRAINS; k++) {
		const prev = rounds[k - 1];
		if (!prev.ready.size) break;
		const cur: Round = { arr: new Map(), ready: new Map(), label: new Map() };
		const bound = () => best.get(target) ?? Infinity;
		for (const trip of net.trips) {
			let board = -1;
			for (let i = 0; i < trip.stops.length; i++) {
				const s = trip.stops[i];
				if (board >= 0) {
					const a = s.arr;
					if (a < (best.get(s.station) ?? Infinity) && a < bound()) {
						best.set(s.station, a);
						cur.arr.set(s.station, a);
						cur.ready.set(s.station, a + CHANGE_MIN);
						cur.label.set(s.station, { kind: 'ride', trip, board, alight: i, prev: k - 1 });
					}
				} else if (i < trip.stops.length - 1) {
					const r = prev.ready.get(s.station);
					if (r !== undefined && r <= s.dep) board = i;
				}
			}
		}
		walkFrom(net, cur, best, [...cur.arr.keys()], target);
		rounds.push(cur);
	}

	const out: Journey[] = [];
	for (let k = 1; k < rounds.length; k++) {
		if (rounds[k].arr.has(target)) out.push(trace(net, rounds, k, target));
	}
	return out;
}

function walkFrom(net: Network, round: Round, best: Map<number, number>, from: number[], target: number) {
	for (const s of from) {
		const a = round.arr.get(s)!;
		for (const w of net.walks.get(s) ?? []) {
			const t = a + w.minutes;
			if (t < (best.get(w.to) ?? Infinity) && t < (best.get(target) ?? Infinity)) {
				best.set(w.to, t);
				round.arr.set(w.to, t);
				round.ready.set(w.to, t);
				round.label.set(w.to, { kind: 'walk', from: s, minutes: w.minutes });
			}
		}
	}
}

function trace(net: Network, rounds: Round[], k: number, target: number): Journey {
	const legs: Leg[] = [];
	let station = target;
	let round = k;
	let walkEnd = 0;
	let walkStart = 0;
	for (;;) {
		const label = rounds[round].label.get(station)!;
		if (label.kind === 'origin') break;
		if (label.kind === 'walk') {
			// A walk is the last step, the first one, or part of a change.
			if (station === target) walkEnd = label.minutes;
			else if (round === 0) walkStart = label.minutes;
			station = label.from;
			continue;
		}
		legs.unshift(leg(net, label.trip, label.board, label.alight));
		station = label.trip.stops[label.board].station;
		round = label.prev;
	}
	const changes: Change[] = [];
	for (let i = 0; i < legs.length - 1; i++) {
		const x = legs[i];
		const y = legs[i + 1];
		const minutes = y.dep - x.arr;
		const walk = x.toCode !== y.fromCode ? walkMinutes(x.toCode, y.fromCode) : null;
		changes.push({
			minutes,
			tight: minutes <= (walk ?? CHANGE_MIN) + 1,
			walk: walk !== null ? { fromName: x.toName, toName: y.fromName, fromLine: x.line, toLine: y.line } : null
		});
	}
	const dep = legs[0].dep - walkStart;
	const arr = legs.at(-1)!.arr + walkEnd;
	return { legs, changes, walkStart, walkEnd, dep, arr, minutes: arr - dep };
}

function walkMinutes(a: string, b: string): number | null {
	return WALKS.find(([p, q]) => (p === a && q === b) || (p === b && q === a))?.[2] ?? null;
}

function leg(net: Network, trip: TripRow, board: number, alight: number): Leg {
	const a = trip.stops[board];
	const b = trip.stops[alight];
	let fast: boolean;
	if (a.pos !== null && b.pos !== null) fast = alight - board < b.pos - a.pos;
	else {
		const seq = net.lineSeq.get(trip.line);
		const sa = seq?.get(a.station);
		const sb = seq?.get(b.station);
		fast = sa !== undefined && sb !== undefined && alight - board < Math.abs(sb - sa);
	}
	return {
		trainId: trip.id,
		number: trip.number,
		line: trip.line,
		fast,
		ac: trip.ac,
		cars: trip.cars,
		towards: net.name.get(trip.dest) ?? '',
		fromCode: net.code.get(a.station)!,
		fromName: net.name.get(a.station)!,
		toCode: net.code.get(b.station)!,
		toName: net.name.get(b.station)!,
		dep: a.dep,
		arr: b.arr,
		pfFrom: a.pf,
		pfTo: b.pf
	};
}

// ---------------------------------------------------------------- journeys

function dominated(j: Journey, by: Journey): boolean {
	return (
		by !== j &&
		by.dep >= j.dep &&
		by.arr <= j.arr &&
		by.legs.length <= j.legs.length &&
		(by.dep > j.dep || by.arr < j.arr || by.legs.length < j.legs.length)
	);
}

/** The next journeys leaving from `from` at or after `after` (service-day
 *  minutes) on weekday `dow`, best first, none worse in every way than another. */
export function journeysOn(db: Database, fromCode: string, toCode: string, dow: number, after: number, limit: number): Journey[] {
	const net = network(db, dow);
	const origin = net.byCode.get(fromCode);
	const target = net.byCode.get(toCode);
	if (origin === undefined || target === undefined || origin === target) return [];
	const found: Journey[] = [];
	let t = after;
	// Each search gives the earliest arrivals from t; searching again just after
	// the first train found walks forward through the day.
	for (let n = 0; n < limit * 4 && found.length < limit * 3; n++) {
		const res = search(net, origin, target, t);
		if (!res.length) break;
		found.push(...res);
		t = Math.min(...res.map((j) => j.dep)) + 1;
	}
	const seen = new Set<string>();
	return found
		.filter((j) => {
			const key = j.legs.map((l) => `${l.trainId}:${l.fromCode}:${l.toCode}`).join('|');
			if (seen.has(key)) return false;
			seen.add(key);
			return true;
		})
		.filter((j, _, list) => !list.some((o) => dominated(j, o)))
		.sort((a, b) => a.dep - b.dep || a.arr - b.arr)
		.slice(0, limit);
}

/** The next journeys from now, running into tomorrow's first trains. */
export function upcomingJourneys(db: Database, fromCode: string, toCode: string, now: { minute: number; dow: number }, limit: number): Journey[] {
	const today = journeysOn(db, fromCode, toCode, now.dow, now.minute, limit);
	if (today.length >= limit) return today;
	const tomorrow = journeysOn(db, fromCode, toCode, (now.dow + 1) % 7, 0, limit - today.length).map((j) => ({
		...j,
		dep: j.dep + 1440,
		arr: j.arr + 1440,
		legs: j.legs.map((l) => ({ ...l, dep: l.dep + 1440, arr: l.arr + 1440 })),
		tomorrow: true
	}));
	return [...today, ...tomorrow];
}
