import { SERVICE_DAY_START_MIN, TIME_ZONE } from './config';

/** A moment expressed the way the timetable counts time. */
export interface ServiceNow {
	/** Minutes since midnight of the service day; 00:30 is 1470. */
	minute: number;
	/** Day of week of the service day, Monday = 0. */
	dow: number;
	/** Calendar date of the service day, YYYY-MM-DD. */
	date: string;
	weekend: boolean;
}

const parts = new Intl.DateTimeFormat('en-GB', {
	timeZone: TIME_ZONE,
	year: 'numeric',
	month: '2-digit',
	day: '2-digit',
	hour: '2-digit',
	minute: '2-digit',
	hourCycle: 'h23',
	weekday: 'short'
});
const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export function serviceNow(at: Date = new Date()): ServiceNow {
	const p = Object.fromEntries(parts.formatToParts(at).map((x) => [x.type, x.value]));
	let minute = Number(p.hour) * 60 + Number(p.minute);
	let dow = DOW.indexOf(p.weekday);
	let date = `${p.year}-${p.month}-${p.day}`;
	if (minute < SERVICE_DAY_START_MIN) {
		// Still yesterday's timetable.
		minute += 1440;
		dow = (dow + 6) % 7;
		const d = new Date(Date.UTC(+p.year, +p.month - 1, +p.day - 1));
		date = d.toISOString().slice(0, 10);
	}
	return { minute, dow, date, weekend: dow >= 5 };
}

export function clock(min: number, h24 = true): string {
	const m = ((min % 1440) + 1440) % 1440;
	const h = Math.floor(m / 60);
	const mm = String(m % 60).padStart(2, '0');
	if (h24) return `${String(h).padStart(2, '0')}:${mm}`;
	const h12 = h % 12 === 0 ? 12 : h % 12;
	return `${h12}:${mm} ${h < 12 ? 'am' : 'pm'}`;
}

/** "4 min", "1 h 5 min" */
export function duration(min: number): string {
	if (min < 60) return `${min} min`;
	const h = Math.floor(min / 60);
	const m = min % 60;
	return m ? `${h} h ${m} min` : `${h} h`;
}

export function dayName(dow: number): string {
	return ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][dow];
}

/** Running days in words, from the 7-character Mon..Sun flag string. */
export function daysLabel(days: string, notOnHolidays = false): string | null {
	const holidays = notOnHolidays ? ' & holidays' : '';
	if (days === '1111111') return notOnHolidays ? 'Not on holidays' : null;
	if (days === '1111110') return `Not on Sundays${holidays}`;
	if (days === '0000001') return 'Sundays only';
	if (days === '1111100') return `Weekdays only${holidays}`;
	const names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].filter((_, i) => days[i] === '1');
	return names.join(', ') + holidays;
}

export function relativeDate(iso: string, now = new Date()): string {
	const then = new Date(iso);
	const days = Math.floor((now.getTime() - then.getTime()) / 86_400_000);
	if (days <= 0) return 'today';
	if (days === 1) return 'yesterday';
	if (days < 30) return `${days} days ago`;
	return then.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function longDate(iso: string): string {
	return new Date(iso + (iso.length === 10 ? 'T00:00:00' : '')).toLocaleDateString('en-IN', {
		day: 'numeric',
		month: 'short',
		year: 'numeric'
	});
}
