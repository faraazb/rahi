<script lang="ts">
	import ArrowDown from '@lucide/svelte/icons/arrow-down';
	import ArrowUp from '@lucide/svelte/icons/arrow-up';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import Star from '@lucide/svelte/icons/star';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { departuresOn, directionDestinations, hasPlatforms, lines, pfLabel, stationByCode, trainsCalling, upcomingDepartures } from '#lib/data/queries.ts';
	import { lineStyle } from '#lib/lines.ts';
	import { href } from '#lib/nav.ts';
	import { clock as appClock } from '#lib/state/clock.svelte.ts';
	import { prefs } from '#lib/state/prefs.svelte.ts';
	import { saved } from '#lib/state/saved.svelte.ts';
	import KindTag from '#lib/ui/KindTag.svelte';
	import LineBadge from '#lib/ui/LineBadge.svelte';
	import { clock } from '#lib/time.ts';

	const db = $derived.by(() => {
		void timetable.revision;
		return timetable.db!;
	});
	const st = $derived(stationByCode(db, page.params.code ?? ''));
	const now = $derived(appClock.now);
	const t = (m: number) => clock(m, prefs.h24);

	let lineCode = $state<string | null>(null);
	const line = $derived(st ? (lineCode && st.lines.includes(lineCode) ? lineCode : st.lines[0]) : null);
	const lineName = (code: string) => lines(db).find((l) => l.code === code)?.name ?? code;

	// Directions that actually have departures here (none "up" at Churchgate).
	const dirs = $derived.by(() => {
		if (!st || !line) return [];
		const towards = lineStyle(line).towards;
		// Lines without a fixed end each way: name the direction after where its trains go.
		const goesTo = (n: number) => {
			const names = directionDestinations(db, st, line, n);
			return names.length > 2 ? `${names.slice(0, 2).join(', ')} …` : names.join(', ') || (n === 1 ? 'Up' : 'Down');
		};
		return (
			[
				{ id: 'up' as const, n: 1, label: `Towards ${towards?.up ?? goesTo(1)}`, icon: ArrowUp },
				{ id: 'down' as const, n: 2, label: `Towards ${towards?.down ?? goesTo(2)}`, icon: ArrowDown }
			] as const
		).filter((d) => departuresOn(db, st, line, d.n, now.dow).length > 0 || departuresOn(db, st, line, d.n, (now.dow + 1) % 7).length > 0);
	});
	const dirParam = $derived(page.url.searchParams.get('dir'));
	const dir = $derived(dirs.find((d) => d.id === dirParam) ?? dirs[0]);

	let limit = $state(20);
	const rows = $derived(st && line && dir ? upcomingDepartures(db, st, line, dir.n, now, limit) : []);
	const calling = $derived(st ? trainsCalling(db, st, now.dow) : 0);
	const showPf = $derived(hasPlatforms(db) && rows.some((r) => r.pf));

	function pickDir(id: 'up' | 'down') {
		limit = 20;
		goto(href.station(st!.code, id), { replace: true, reset: false });
	}
	const due = (m: number) => {
		const d = m - now.minute;
		if (d <= 0) return 'now';
		if (d < 60) return `${d} min`;
		return t(m);
	};
	const isSaved = $derived(st ? saved.isSaved(st.code) : false);
</script>

{#if !st}
	<div class="page">
		<header class="page-head">
			<div class="head-row"><a class="back" href={href.trains()} aria-label="Back"><ChevronLeft size={24} /></a></div>
		</header>
		<main class="page-main"><p class="note">No station with code “{page.params.code}”.</p></main>
	</div>
{:else}
	<div class="page">
		<header class="page-head">
			<div class="head-row">
				<a class="back" href={href.trains()} aria-label="Back"><ChevronLeft size={24} /></a>
				<div class="head-title">
					<h1 class="name">{st.name}</h1>
					<span class="head-sub">
						{#each st.lines as l (l)}<LineBadge line={l} size="sm" />{/each}
						<span class="num">{st.code} · {calling} trains today</span>
					</span>
				</div>
				<button
					type="button"
					class="round-btn star"
					class:on={isSaved}
					aria-pressed={isSaved}
					aria-label={isSaved ? 'Remove from saved stations' : 'Save station'}
					onclick={() => saved.toggleStation(st.code)}
				>
					<Star size={20} fill={isSaved ? 'currentColor' : 'none'} />
				</button>
			</div>
			{#if st.lines.length > 1}
				<div class="tabs" role="tablist" aria-label="Line">
					{#each st.lines as l (l)}
						<button type="button" role="tab" aria-selected={l === line} title={lineName(l)} onclick={() => (lineCode = l)}>
							<span class="ldot" style:background={lineStyle(l).color}></span><span class="tl"
								>{st.lines.length > 2 ? (lineStyle(l).short ?? lineName(l)) : lineName(l)}</span
							>
						</button>
					{/each}
				</div>
			{/if}
			{#if dirs.length}
				<div class="dirs" role="group" aria-label="Direction">
					{#each dirs as d (d.id)}
						{@const Icon = d.icon}
						<button type="button" aria-pressed={d.id === dir?.id} onclick={() => pickDir(d.id)}><Icon size={18} />{d.label}</button>
					{/each}
				</div>
			{/if}
		</header>
		<main class="page-main">
			<section class="board card" class:with-pf={showPf} aria-label="Departures">
				<div class="grid th">
					<span>Time</span><span>Destination</span>{#if showPf}<span class="center">PF</span>{/if}<span class="right">Due</span>
				</div>
				{#each rows as r (r.trainId + ':' + r.time)}
					<a class="grid tr" href={href.train(r.trainId, st.code)}>
						<span class="time num">{t(r.time)}</span>
						<span class="dest">
							<span class="dn">{r.dest}</span>
							<span class="meta"><KindTag fast={r.fast} ac={r.ac} size="sm" />{r.cars ? `${r.cars} car` : ''}{r.tomorrow ? ' · tomorrow' : ''}</span>
						</span>
						{#if showPf}
							<span class="pf num" aria-label={r.pf ? `Platform ${pfLabel(r.pf)}` : 'Platform not known'}>{pfLabel(r.pf) ?? '–'}</span>
						{/if}
						<span class="due num" class:soon={r.time - now.minute < 10 && !r.tomorrow}>{due(r.time)}</span>
					</a>
				{:else}
					<p class="note pad">No more departures in this direction today.</p>
				{/each}
				{#if rows.length >= limit}
					<button type="button" class="more" onclick={() => (limit += 30)}>Show later trains</button>
				{/if}
			</section>
		</main>
	</div>
{/if}

<style>
	.note {
		color: var(--text2);
		padding: 8px 4px;
	}
	.note.pad {
		padding: 18px 16px;
	}
	.head-title .name {
		font-size: 1.375rem;
		letter-spacing: -0.02em;
	}
	.star.on {
		color: var(--warn);
	}
	.tabs {
		display: grid;
		/* One row, however many lines call here (Nerul: Harbour, Trans-Harbour, Uran). */
		grid-auto-flow: column;
		grid-auto-columns: minmax(0, 1fr);
		gap: 4px;
		margin: 0 4px;
		padding: 4px;
		border-radius: 14px;
		background: var(--surface2);
	}
	.tabs button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		height: 40px;
		border: 0;
		border-radius: 10px;
		background: transparent;
		color: var(--text2);
		font-size: 0.875rem;
		font-weight: 700;
	}
	.tabs button {
		min-width: 0;
		padding: 0 8px;
	}
	.tl {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.ldot {
		flex: none;
	}
	.tabs button[aria-selected='true'] {
		background: var(--surface);
		color: var(--text);
		box-shadow: var(--shadow);
	}
	.ldot {
		width: 8px;
		height: 8px;
		border-radius: 999px;
	}
	.dirs {
		display: flex;
		gap: 8px;
		padding: 0 4px;
	}
	.dirs button {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		height: 40px;
		padding: 0 10px;
		border-radius: 999px;
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text2);
		font-size: 0.875rem;
		font-weight: 700;
		white-space: nowrap;
	}
	.dirs button[aria-pressed='true'] {
		border-color: var(--text);
		background: var(--text);
		color: var(--surface);
	}
	.board {
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.grid {
		display: grid;
		grid-template-columns: 64px minmax(0, 1fr) 64px;
		gap: 10px;
		align-items: center;
		padding: 8px 16px;
	}
	.th {
		padding-top: 10px;
		padding-bottom: 10px;
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text3);
		background: var(--surface2);
	}
	.with-pf .grid {
		grid-template-columns: 56px minmax(0, 1fr) 44px 52px;
	}
	.right {
		text-align: right;
	}
	.center {
		text-align: center;
	}
	.pf {
		justify-self: center;
		min-width: 34px;
		height: 34px;
		padding: 0 4px;
		display: grid;
		place-items: center;
		border-radius: 10px;
		background: var(--surface2);
		font-size: 0.9375rem;
		font-weight: 800;
		white-space: nowrap;
	}
	.tr {
		min-height: 60px;
		border-top: 1px solid var(--border);
	}
	.th + .tr {
		border-top: 0;
	}
	.time {
		font-size: 1.0625rem;
		font-weight: 800;
	}
	.dest {
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.dn {
		font-size: 0.9375rem;
		font-weight: 700;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.meta {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 0.75rem;
		color: var(--text3);
	}
	.due {
		text-align: right;
		font-size: 0.8125rem;
		font-weight: 700;
		color: var(--text2);
	}
	.due.soon {
		color: var(--primary);
	}
	.more {
		min-height: 48px;
		border: 0;
		border-top: 1px solid var(--border);
		background: transparent;
		color: var(--primary);
		font-size: 0.875rem;
		font-weight: 700;
	}
</style>
