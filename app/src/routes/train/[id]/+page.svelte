<script lang="ts">
	import Bell from '@lucide/svelte/icons/bell';
	import BellRing from '@lucide/svelte/icons/bell-ring';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import Clock from '@lucide/svelte/icons/clock';
	import Share2 from '@lucide/svelte/icons/share-2';
	import TrainFront from '@lucide/svelte/icons/train-front';
	import X from '@lucide/svelte/icons/x';
	import { page } from '$app/state';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { doorsLabel, pfLabel, skipsStations, train as getTrain, type TrainStop } from '#lib/data/queries.ts';
	import { lineStyle } from '#lib/lines.ts';
	import { href } from '#lib/nav.ts';
	import { clock as appClock } from '#lib/state/clock.svelte.ts';
	import { prefs } from '#lib/state/prefs.svelte.ts';
	import { LEAD_MIN, reminder } from '#lib/state/reminder.svelte.ts';
	import KindTag from '#lib/ui/KindTag.svelte';
	import { clock, dayName, daysLabel, duration } from '#lib/time.ts';

	const db = $derived.by(() => {
		void timetable.revision;
		return timetable.db!;
	});
	const id = $derived(Number(page.params.id));
	const tr = $derived(getTrain(db, id));
	const t = (m: number) => clock(m, prefs.h24);
	const now = $derived(appClock.now);

	// Your part of the journey: ?from&to, else the whole run.
	const fromIdx = $derived.by(() => {
		if (!tr) return 0;
		const i = tr.stops.findIndex((s) => s.code === page.url.searchParams.get('from'));
		return i >= 0 ? i : 0;
	});
	const toIdx = $derived.by(() => {
		if (!tr) return 0;
		const i = tr.stops.findIndex((s, k) => k > fromIdx && s.code === page.url.searchParams.get('to'));
		return i >= 0 ? i : tr.stops.length - 1;
	});
	const fromStop = $derived(tr?.stops[fromIdx]);
	const toStop = $derived(tr?.stops[toIdx]);
	// Where you get off, the arrival counts (a halt can be 15 minutes long).
	const toTime = $derived(toStop ? (toStop.arr ?? toStop.time) : 0);
	const runsToday = $derived(!!tr && tr.days[now.dow] === '1');
	const ac = $derived(!!tr && tr.ac && !(tr.acWeekdaysOnly && now.weekend));

	// Where the train is by the timetable (only meaningful on a running day).
	const lastPassed = $derived.by(() => {
		if (!tr || !runsToday) return -1;
		let k = -1;
		tr.stops.forEach((s, i) => {
			if (s.time <= now.minute) k = i;
		});
		return k;
	});
	const running = $derived(!!tr && runsToday && lastPassed >= 0 && lastPassed < tr.stops.length - 1);
	const phase = $derived.by((): 'before' | 'riding' | 'after' | 'notToday' => {
		if (!fromStop || !toStop) return 'notToday';
		if (!runsToday) return 'notToday';
		if (now.minute < fromStop.time) return 'before';
		if (now.minute < toTime) return 'riding';
		return 'after';
	});
	const pct = $derived.by(() => {
		if (!fromStop || !toStop) return 0;
		if (phase === 'before' || phase === 'notToday') return 0;
		if (phase === 'after') return 100;
		return Math.round((100 * (now.minute - fromStop.time)) / Math.max(1, toTime - fromStop.time));
	});
	const position = $derived.by(() => {
		if (!tr || phase === 'notToday') return '';
		if (phase === 'before') return lastPassed < 0 ? 'Not started yet' : `Near ${tr.stops[lastPassed].name}`;
		if (phase === 'after') return 'Arrived';
		const a = tr.stops[lastPassed];
		const b = tr.stops[lastPassed + 1];
		if (a.time === now.minute) return `At ${a.name}`;
		return `Between ${a.name} & ${b.name}`;
	});
	const color = $derived(tr ? lineStyle(tr.line).color : 'var(--primary)');
	// Fast for your part of the run: it skips a station between your two.
	const segFast = $derived.by(() => {
		if (!tr || !fromStop || !toStop) return false;
		if (fromStop.pos !== null && toStop.pos !== null) return skipsStations(toIdx - fromIdx, fromStop.pos, toStop.pos);
		if (fromStop.lineSeq === null || toStop.lineSeq === null) return tr.fast;
		return skipsStations(toIdx - fromIdx, null, null, fromStop.lineSeq, toStop.lineSeq);
	});

	const facts = $derived.by(() => {
		if (!tr) return [];
		const out: string[] = [];
		const days = daysLabel(tr.days, tr.notOnHolidays);
		out.push(days ? `Runs: ${days}` : 'Runs every day');
		if (tr.ac && tr.acWeekdaysOnly) out.push('AC on weekdays; an ordinary train on Saturdays and Sundays');
		else if (tr.ac) out.push('Air-conditioned');
		if (tr.ladies) out.push('Ladies special');
		if (tr.operator === 'CR') out.push('A Central Railway (Harbour) train on Western Railway tracks');
		// Not suburban locals: Indian Railways MEMU / hill-railway trains, timed from NTES.
		if (tr.line === 'DVP' || tr.line === 'NM') {
			out.push(`Indian Railways ${tr.line === 'NM' ? 'hill railway train' : 'MEMU'}${tr.notes ? ` “${tr.notes}”` : ''}, timed from NTES`);
		}
		const first = tr.stops[0];
		const last = tr.stops.at(-1)!;
		out.push(`${first.name} ${t(first.time)} to ${last.name} ${t(last.time)}`);
		if (tr.destTimeMissing) out.push(`Goes on to ${tr.dest}; the timetable prints no time there`);
		return out;
	});

	const reminderOn = $derived(reminder.active?.trainId === id);
	const canRemind = $derived(phase === 'before' || (phase === 'riding' && !!toStop && toTime - now.minute > LEAD_MIN));

	let copied = $state(false);
	async function share() {
		const url = location.href;
		const title = tr ? `${t(fromStop!.time)} ${tr.dest} ${tr.fast ? 'fast' : 'slow'}` : 'Train';
		if (navigator.share) {
			try {
				await navigator.share({ title, url });
			} catch {
				/* dismissed */
			}
		} else {
			await navigator.clipboard?.writeText(url);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}

	/** Platform line under a stop, as in the design: "PF 3 · doors on right". */
	function platformLine(s: TrainStop, i: number, passed: boolean): string | null {
		const pf = pfLabel(s.pf);
		if (passed) return pf ? `Departed PF ${pf}` : `Departed ${t(s.time)}`;
		if (!pf) return null;
		const last = i === tr!.stops.length - 1;
		// The design drops doors at the terminus, unless that is where you get off.
		const doors = last && i !== toIdx ? null : doorsLabel(s.doors);
		return [`PF ${pf}`, last ? 'terminates' : null, doors].filter(Boolean).join(' · ');
	}

	function stopState(i: number): 'passed' | 'next' | 'future' {
		if (!runsToday || lastPassed < 0) return 'future';
		if (i <= lastPassed) return 'passed';
		return 'future';
	}
	const inSegment = (i: number) => i >= fromIdx && i <= toIdx;
	const minsAgo = $derived(lastPassed >= 0 && tr ? now.minute - tr.stops[lastPassed].time : 0);
	const back = $derived(
		page.url.searchParams.get('to')
			? href.trains(page.url.searchParams.get('from'), page.url.searchParams.get('to'))
			: page.url.searchParams.get('from')
				? href.station(page.url.searchParams.get('from')!)
				: href.trains()
	);
</script>

{#snippet stopRow(s: TrainStop, i: number)}
	{@const st = stopState(i)}
	{@const sub = st === 'passed' && !inSegment(i) ? null : platformLine(s, i, st === 'passed')}
	<li class:muted={!inSegment(i)} class:passed={st === 'passed'}>
		<span class="t num">{t(s.time)}</span>
		<span class="rail" aria-hidden="true" style:--c={color}>
			<span class="seg top" class:on={i > 0 && st === 'passed'} class:none={i === 0}></span>
			<span class="dot" class:end={i === fromIdx || i === toIdx}></span>
			<span class="seg bot" class:on={i < lastPassed} class:none={i === tr!.stops.length - 1}></span>
		</span>
		<span class="what">
			<span class="names">
				<span class="name">{s.name}</span>
				{#if s.arr !== null}<span class="sub num">Arrives {t(s.arr)} · leaves {t(s.time)}</span>{/if}
				{#if sub}<span class="sub" class:pf-strong={i === toIdx && st !== 'passed'}>{sub}</span>{/if}
			</span>
			{#if i === fromIdx}<span class="tag">Board</span>{/if}
			{#if i === toIdx}<span class="tag strong">Get off</span>{/if}
		</span>
	</li>
	{#if running && i === lastPassed}
		<li class="train-row">
			<span class="t"></span>
			<span class="rail" aria-hidden="true" style:--c={color}>
				<span class="seg top on"></span>
				<span class="engine"><TrainFront size={16} /></span>
				<span class="seg bot"></span>
			</span>
			<span class="what">
				<span class="names">
					<span class="name now">Left {s.name} {minsAgo <= 0 ? 'just now' : `${minsAgo} min ago`}</span>
					<span class="sub">By the timetable · next {tr!.stops[i + 1].name} at {t(tr!.stops[i + 1].time)}</span>
				</span>
			</span>
		</li>
	{/if}
{/snippet}

{#if !tr || !fromStop || !toStop}
	<div class="page">
		<header class="page-head">
			<div class="head-row"><a class="back" href={href.trains()} aria-label="Back"><ChevronLeft size={24} /></a></div>
		</header>
		<main class="page-main"><p class="note">This train isn't in the current timetable. It may have been renumbered in an update.</p></main>
	</div>
{:else}
	<div class="page">
		<header class="page-head">
			<div class="head-row">
				<a class="back" href={back} aria-label="Back"><ChevronLeft size={24} /></a>
				<div class="head-title">
					<h1>{t(fromStop.time)} {tr.dest} {tr.fast ? 'Fast' : 'Slow'}</h1>
					<span class="head-sub">
						<span class="ldot" style:background={color}></span>{tr.lineName}{tr.cars ? ` · ${tr.cars} car` : ''}{fromStop.pf ? ` · PF ${pfLabel(fromStop.pf)}` : ''} · No. {tr.number}
					</span>
				</div>
				<button type="button" class="round-btn" aria-label={copied ? 'Link copied' : 'Share train'} onclick={share}><Share2 size={20} /></button>
			</div>
		</header>

		<main class="page-main">
			<section class="status card" aria-label="Journey">
				<div class="row between">
					<span class="pill"><Clock size={15} strokeWidth={2.4} />Timetable</span>
					<KindTag fast={segFast} {ac} />
				</div>
				{#if phase === 'notToday'}
					<div class="big-row">
						<div class="col">
							<span class="cap">Doesn't run today</span>
							<span class="big small">{dayName(now.dow)}</span>
						</div>
					</div>
				{:else}
					<div class="big-row">
						<div class="col">
							<span class="cap">
								{phase === 'before' ? `Leaves ${fromStop.name} in` : phase === 'riding' ? `Reaches ${toStop.name} in` : `Reached ${toStop.name} at`}
							</span>
							<span class="big num">
								{phase === 'before' ? duration(fromStop.time - now.minute) : phase === 'riding' ? duration(toTime - now.minute) : t(toTime)}
							</span>
						</div>
						<div class="col end">
							<span class="cap">{phase === 'before' ? 'Departs' : 'Arrives'}</span>
							<span class="mid num">{phase === 'before' ? t(fromStop.time) : t(toTime)}</span>
						</div>
					</div>
				{/if}
				<div class="progress">
					<div class="track" aria-hidden="true">
						<div class="fill" style:width="{pct}%" style:background={color}></div>
						<div class="knob" style:left="{pct}%" style:border-color={color}></div>
					</div>
					<div class="labels">
						<span>{fromStop.name}</span><span class="pos">{position}</span><span>{toStop.name}</span>
					</div>
				</div>
			</section>

			<section class="card about" aria-labelledby="about-h">
				<h2 id="about-h">About this train</h2>
				<ul>
					{#each facts as f (f)}<li>{f}</li>{/each}
				</ul>
			</section>

			<section class="card stops" aria-labelledby="stops-h">
				<h2 id="stops-h">Stops <span class="count">{toIdx - fromIdx} stops · {duration(toTime - fromStop.time)}</span></h2>
				<ol>
					{#each tr.stops as s, i (s.seq)}
						{@render stopRow(s, i)}
					{/each}
				</ol>
			</section>

			{#if reminder.fired}
				<div class="banner" role="status">
					<BellRing size={18} /><span>{reminder.fired}</span>
					<button type="button" aria-label="Dismiss" onclick={() => (reminder.fired = null)}><X size={18} /></button>
				</div>
			{/if}
		</main>

		<div class="actions">
			<button
				type="button"
				class="remind"
				class:on={reminderOn}
				aria-pressed={reminderOn}
				disabled={!reminderOn && !canRemind}
				onclick={() => (reminderOn ? reminder.clear() : reminder.set(id, toStop.name, toTime))}
			>
				{#if reminderOn}
					<BellRing size={20} />Reminder on · {LEAD_MIN} min before {toStop.name}
				{:else}
					<Bell size={20} />Remind me before {toStop.name}
				{/if}
			</button>
		</div>
	</div>
{/if}

<style>
	.note {
		color: var(--text2);
		padding: 8px 4px;
	}
	.ldot {
		flex: none;
		width: 8px;
		height: 8px;
		border-radius: 999px;
	}
	.page-main {
		padding-top: 8px;
		gap: 16px;
	}
	.status {
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 18px;
		border-radius: 24px;
		box-shadow: var(--shadow);
	}
	.row.between {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}
	.pill {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 5px 10px;
		border-radius: 999px;
		font-size: 0.8125rem;
		font-weight: 700;
		background: var(--surface2);
		color: var(--text2);
	}
	.big-row {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: 12px;
	}
	.col {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}
	.col.end {
		align-items: flex-end;
	}
	.cap {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text3);
	}
	.big {
		font-size: 2.5rem;
		line-height: 1;
		font-weight: 800;
		letter-spacing: -0.03em;
	}
	.big.small {
		font-size: 1.75rem;
	}
	.mid {
		font-size: 1.375rem;
		font-weight: 800;
	}
	.progress {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.track {
		position: relative;
		height: 6px;
		border-radius: 999px;
		background: var(--surface2);
	}
	.fill {
		position: absolute;
		inset: 0 auto 0 0;
		border-radius: 999px;
	}
	.knob {
		position: absolute;
		top: 50%;
		width: 16px;
		height: 16px;
		margin: -8px 0 0 -8px;
		border-radius: 999px;
		background: var(--surface);
		border: 3px solid;
	}
	.labels {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text3);
	}
	.pos {
		text-align: center;
	}

	.about {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	h2 {
		font-size: 0.9375rem;
		font-weight: 800;
	}
	.about ul {
		margin: 0;
		padding-left: 18px;
		display: flex;
		flex-direction: column;
		gap: 4px;
		color: var(--text2);
		font-size: 0.875rem;
	}

	.stops {
		padding: 8px 16px;
	}
	.stops h2 {
		margin: 8px 0 4px;
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}
	.count {
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text3);
	}
	ol {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.stops li {
		display: flex;
		align-items: stretch;
		gap: 12px;
		min-height: 52px;
	}
	.t {
		flex: none;
		width: 52px;
		display: flex;
		align-items: center;
		justify-content: flex-end;
		font-size: 0.875rem;
		font-weight: 700;
	}
	.rail {
		flex: none;
		width: 22px;
		display: flex;
		flex-direction: column;
		align-items: center;
	}
	.seg {
		flex: 1;
		width: 3px;
		background: var(--border);
	}
	.seg.on {
		background: var(--c);
	}
	.seg.none {
		visibility: hidden;
	}
	.dot {
		flex: none;
		width: 12px;
		height: 12px;
		border-radius: 999px;
		background: var(--surface);
		border: 3px solid var(--text3);
	}
	.dot.end {
		width: 14px;
		height: 14px;
		border-color: var(--c);
	}
	.passed .dot {
		background: var(--c);
		border-color: var(--c);
	}
	.engine {
		flex: none;
		width: 30px;
		height: 30px;
		margin: 2px 0;
		display: grid;
		place-items: center;
		border-radius: 999px;
		background: var(--c);
		color: var(--on-line);
	}
	.what {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 8px 0;
	}
	.names {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.name {
		font-size: 0.9375rem;
		font-weight: 700;
	}
	.name.now {
		color: var(--c, var(--primary));
		font-weight: 800;
	}
	.train-row .name.now {
		color: var(--primary);
	}
	.sub {
		font-size: 0.75rem;
		color: var(--text3);
	}
	.sub.pf-strong {
		color: var(--text2);
		font-weight: 700;
	}
	.muted .name,
	.muted .t {
		color: var(--text3);
		font-weight: 600;
	}
	.tag {
		flex: none;
		padding: 3px 8px;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 700;
		background: var(--surface2);
		color: var(--text2);
	}
	.tag.strong {
		background: var(--primary-soft);
		color: var(--on-primary-soft);
	}
	.banner {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 14px;
		border-radius: 16px;
		background: var(--primary-soft);
		color: var(--on-primary-soft);
		font-weight: 700;
		font-size: 0.875rem;
	}
	.banner span {
		flex: 1;
	}
	.banner button {
		border: 0;
		background: transparent;
		color: inherit;
		display: grid;
	}

	.actions {
		flex: none;
		display: flex;
		gap: 10px;
		padding: 12px 16px calc(env(safe-area-inset-bottom, 0px) + 14px);
		background: var(--nav-bg);
		border-top: 1px solid var(--border);
	}
	.remind {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		height: 52px;
		border-radius: 16px;
		border: 0;
		background: var(--primary);
		color: var(--on-primary);
		font-size: 0.9375rem;
		font-weight: 700;
	}
	.remind.on {
		background: var(--primary-soft);
		color: var(--on-primary-soft);
		border: 1px solid var(--primary);
	}
	.remind:disabled {
		background: var(--surface2);
		color: var(--text3);
		cursor: default;
	}
	@media (min-width: 900px) {
		.actions {
			background: transparent;
			border: 0;
			padding: 0 16px;
		}
	}
</style>
