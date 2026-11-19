/** Display facts about each line the timetable can contain. The database
 *  carries the line's code and name; how it is drawn lives here. */
export interface LineStyle {
	/** Badge letter(s), as on station signage: W, C, H, TH. */
	badge: string;
	/** Short name for tight places (a station on three lines). */
	short?: string;
	/** CSS custom property holding the line colour for the current theme. */
	color: string;
	/** Where "up" and "down" trains are heading, in riders' words. Left out
	 *  for lines where neither direction has one end (the Vasai–Diva–Panvel
	 *  MEMUs run Diva → Vasai and Roha → Diva as "up"); screens then name the
	 *  direction after where its trains actually go. */
	towards?: { up: string; down: string };
}

export const LINE_STYLES: Record<string, LineStyle> = {
	WR: { badge: 'W', color: 'var(--l-w)', towards: { up: 'Churchgate', down: 'Virar' } },
	CR: { badge: 'C', color: 'var(--l-c)', towards: { up: 'CSMT', down: 'Kalyan' } },
	HR: { badge: 'H', short: 'Harbour', color: 'var(--l-h)', towards: { up: 'CSMT', down: 'Panvel' } },
	THR: { badge: 'TH', short: 'Trans-Hbr', color: 'var(--l-t)', towards: { up: 'Thane', down: 'Vashi' } },
	UR: { badge: 'U', short: 'Uran', color: 'var(--l-u)', towards: { up: 'Nerul / Belapur', down: 'Uran' } },
	PUNE: { badge: 'P', short: 'Pune', color: 'var(--l-p)', towards: { up: 'Lonavala', down: 'Pune' } },
	DVP: { badge: 'VP', short: 'MEMU', color: 'var(--l-vp)' },
	NM: { badge: 'NM', short: 'Matheran', color: 'var(--l-nm)' },
	MON: { badge: 'Mo', color: 'var(--l-mo)', towards: { up: 'Chembur', down: 'Wadala' } }
};

export function lineStyle(code: string): LineStyle {
	return LINE_STYLES[code] ?? { badge: code.slice(0, 2), color: 'var(--text2)' };
}
