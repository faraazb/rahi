<script lang="ts">
	import ArrowLeftRight from '@lucide/svelte/icons/arrow-left-right';
	import ArrowRight from '@lucide/svelte/icons/arrow-right';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Clock from '@lucide/svelte/icons/clock';
	import Search from '@lucide/svelte/icons/search';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { upcomingJourneys } from '#lib/data/planner.ts';
	import { lines, searchStations, stationByCode, stations, tripsOn, withReturns, type Station, type Trip } from '#lib/data/queries.ts';
	import Connections from '#lib/home/Connections.svelte';
	import ReturnLegend from '#lib/ui/ReturnLegend.svelte';
	import { href } from '#lib/nav.ts';
	import { clock } from '#lib/state/clock.svelte.ts';
	import { routeKey, saved } from '#lib/state/saved.svelte.ts';
	import LineBadge from '#lib/ui/LineBadge.svelte';
	import TrainCard from '#lib/trains/TrainCard.svelte';
	import { longDate } from '#lib/time.ts';

	const db = $derived.by(() => {
		void timetable.revision;
		return timetable.db!;
	});
	const fromCode = $derived(page.url.searchParams.get('from'));
	const toCode = $derived(page.url.searchParams.get('to'));
	const from = $derived(fromCode ? stationByCode(db, fromCode) : null);
	const to = $derived(toCode ? stationByCode(db, toCode) : null);

	// ------------------------------------------------ between two stations
	type Filter = 'all' | 'fast' | 'slow' | 'ac' | '15';
	const FILTERS: { id: Filter; label: string; test: (t: Trip) => boolean }[] = [
		{ id: 'all', label: 'All', test: () => true },
		{ id: 'fast', label: 'Fast', test: (t) => t.fast },
		{ id: 'slow', label: 'Slow', test: (t) => !t.fast },
		{ id: 'ac', label: 'AC', test: (t) => t.ac },
		{ id: '15', label: '15 car', test: (t) => t.cars === 15 }
	];
	let filter = $state<Filter>('all');
	let showEarlier = $state(false);

	const now = $derived(clock.now);
	const all = $derived(from && to ? withReturns(db, tripsOn(db, from, to, now.dow), from, now.dow) : []);
	const shown = $derived(all.filter(FILTERS.find((f) => f.id === filter)!.test));
	const past = $derived(shown.filter((t) => t.dep < now.minute));
	const upcoming = $derived(shown.filter((t) => t.dep >= now.minute));
	const tomorrow = $derived.by(() => {
		if (!from || !to || upcoming.length >= 3) return [];
		const test = FILTERS.find((f) => f.id === filter)!.test;
		const next = tripsOn(db, from, to, (now.dow + 1) % 7)
			.filter(test)
			.slice(0, 5)
			.map((t) => ({ ...t, dep: t.dep + 1440, arr: t.arr + 1440, tomorrow: true }));
		return withReturns(db, next, from, now.dow);
	});
	const anyReturn = $derived([...all, ...tomorrow].some((t) => t.ret));
	// No train runs between them today: journeys with changes instead.
	const direct = $derived(all.length > 0 || (from && to ? tripsOn(db, from, to, (now.dow + 1) % 7).length > 0 : false));
	const journeys = $derived(from && to && !direct ? upcomingJourneys(db, from.code, to.code, now, 6) : []);
	const inHour = $derived(upcoming.filter((t) => t.dep < now.minute + 60).length);
	const visiblePast = $derived(showEarlier ? past : past.slice(-1));
	const lineNames = $derived(
		[...new Set(all.map((t) => t.line))]
			.map((c) => lines(db).find((l) => l.code === c)?.name)
			.filter(Boolean)
			.join(' & ')
	);
	const effective = $derived(timetable.manifest?.lines.find((l) => l.name === lineNames)?.effective_from);

	function swapRoute() {
		goto(href.trains(toCode, fromCode), { replace: true, reset: false });
	}

	// ------------------------------------------------ station finder
	let q = $state('');
	const found = $derived(q.trim() ? searchStations(db, q, null, 12) : []);
	const byLine = $derived(
		lines(db).map((l) => ({ ...l, stations: stations(db).filter((s) => s.lines.includes(l.code)) }))
	);
	const yourRoutes = $derived(
		[...saved.pinned, ...(saved.last && !saved.isPinned(saved.last) ? [saved.last] : [])]
			.map((r) => ({ r, a: stationByCode(db, r.from), b: stationByCode(db, r.to) }))
			.filter((x): x is { r: typeof x.r; a: Station; b: Station } => !!x.a && !!x.b)
	);
	const savedStations = $derived(saved.stations.map((c) => stationByCode(db, c)).filter((s): s is Station => !!s));
</script>

{#if from && to}
	<div class="page">
		<header class="page-head">
			<div class="head-row">
				<a class="back" href={href.home() + `?from=${from.code}&to=${to.code}`} aria-label="Back"><ChevronLeft size={24} /></a>
				<div class="head-title">
					<h1><span class="clip">{from.name}</span><ArrowRight size={18} strokeWidth={2.4} /><span class="clip">{to.name}</span></h1>
					<span class="head-sub">Today · {lineNames ? `${lineNames} line` : direct ? 'No direct trains' : 'With changes'}{effective ? ` · timetable from ${longDate(effective)}` : ''}</span>
				</div>
				<button type="button" class="round-btn" aria-label="Swap direction" onclick={swapRoute}><ArrowLeftRight size={20} /></button>
			</div>
			{#if direct}
				<div class="chips" role="group" aria-label="Filter trains">
					{#each FILTERS as f (f.id)}
						<button type="button" class="chip" aria-pressed={filter === f.id} onclick={() => (filter = f.id)}>{f.label}</button>
					{/each}
				</div>
			{/if}
		</header>
		<main class="page-main list">
			{#if !direct}
				{#if journeys.length}
					<Connections {journeys} nowMinute={now.minute} />
				{:else}
					<p class="note">No trains between these stations, even with changes.</p>
				{/if}
			{:else}
			<div class="countrow">
				<span class="num">{inHour === 1 ? '1 train' : `${inHour} trains`} in the next hour</span>
				{#if anyReturn}<ReturnLegend />{:else}<span class="sched"><Clock size={14} strokeWidth={2.4} />Scheduled times</span>{/if}
			</div>
			{#if past.length > 1 && !showEarlier}
				<button type="button" class="earlier" onclick={() => (showEarlier = true)}>
					Show {past.length - 1} earlier {past.length - 1 === 1 ? 'train' : 'trains'}
				</button>
			{/if}
			{#each visiblePast as trip (trip.trainId)}
				<TrainCard {trip} from={from.code} to={to.code} nowMinute={now.minute} state="departed" />
			{/each}
			{#each upcoming as trip, i (trip.trainId)}
				<TrainCard {trip} from={from.code} to={to.code} nowMinute={now.minute} state={i === 0 ? 'next' : 'later'} />
			{/each}
			{#if !upcoming.length}
				<p class="note">{shown.length ? 'No more trains today.' : 'No trains match this filter today.'}</p>
			{/if}
			{#if tomorrow.length}
				<h2 class="eyebrow">Tomorrow</h2>
				{#each tomorrow as trip, i (trip.trainId)}
					<TrainCard {trip} from={from.code} to={to.code} nowMinute={now.minute} state={i === 0 && !upcoming.length ? 'next' : 'later'} />
				{/each}
			{/if}
			{/if}
		</main>
	</div>
{:else}
	<div class="page">
		<header class="page-head finder-head">
			<h1 class="big-title">Trains</h1>
			<label class="search">
				<Search size={20} />
				<span class="visually-hidden">Find a station</span>
				<input type="search" placeholder="Find a station" autocomplete="off" bind:value={q} />
			</label>
		</header>
		<main class="page-main">
			{#if q.trim()}
				<div class="card rows">
					{#each found as st (st.code)}
						<a class="row" href={href.station(st.code)}>
							<span class="name">{st.name}<span class="code">{st.code}</span></span>
							{#each st.lines as line (line)}<LineBadge {line} />{/each}
							<ChevronRight size={18} />
						</a>
					{:else}
						<p class="note pad">No station matches “{q}”.</p>
					{/each}
				</div>
			{:else}
				{#if yourRoutes.length}
					<h2 class="eyebrow">Your routes</h2>
					<div class="card rows">
						{#each yourRoutes as x (routeKey(x.r))}
							<a class="row" href={href.trains(x.r.from, x.r.to)}>
								<span class="name">{x.a.name}<ArrowRight size={15} strokeWidth={2.4} />{x.b.name}</span>
								<ChevronRight size={18} />
							</a>
						{/each}
					</div>
				{/if}
				{#if savedStations.length}
					<h2 class="eyebrow">Saved stations</h2>
					<div class="card rows">
						{#each savedStations as st (st.code)}
							<a class="row" href={href.station(st.code)}>
								<span class="name">{st.name}<span class="code">{st.code}</span></span>
								<ChevronRight size={18} />
							</a>
						{/each}
					</div>
				{/if}
				{#each byLine as l (l.code)}
					<h2 class="eyebrow line-h"><LineBadge line={l.code} size="sm" />{l.name} line</h2>
					<div class="card rows">
						{#each l.stations as st (st.code)}
							<a class="row" href={href.station(st.code)}>
								<span class="name">{st.name}<span class="code">{st.code}</span></span>
								<ChevronRight size={18} />
							</a>
						{/each}
					</div>
				{/each}
			{/if}
		</main>
	</div>
{/if}

<style>
	.clip {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.chips {
		display: flex;
		gap: 8px;
		overflow-x: auto;
		margin: 0 -12px;
		padding: 0 16px;
		scrollbar-width: none;
	}
	.chip {
		flex: none;
		height: 36px;
		padding: 0 14px;
		border-radius: 999px;
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text2);
		font-size: 0.875rem;
		font-weight: 700;
	}
	.chip[aria-pressed='true'] {
		border-color: var(--text);
		background: var(--text);
		color: var(--surface);
	}
	.list {
		gap: 10px;
	}
	.countrow {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0 4px;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text3);
	}
	.sched {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.earlier {
		align-self: center;
		height: 36px;
		padding: 0 14px;
		border-radius: 999px;
		border: 1px solid var(--border);
		background: transparent;
		color: var(--text2);
		font-size: 0.8125rem;
		font-weight: 700;
	}
	.note {
		padding: 8px 4px;
		color: var(--text3);
		font-size: 0.9375rem;
	}
	.note.pad {
		padding: 18px 16px;
	}

	.finder-head {
		padding-left: 16px;
		padding-right: 16px;
		padding-top: calc(env(safe-area-inset-top, 0px) + 40px);
		gap: 16px;
	}
	.big-title {
		font-size: 2rem;
		line-height: 1.1;
		font-weight: 800;
		letter-spacing: -0.025em;
	}
	.search {
		display: flex;
		align-items: center;
		gap: 10px;
		height: 52px;
		padding: 0 16px;
		border-radius: 16px;
		background: var(--surface);
		border: 1px solid var(--border);
		color: var(--text3);
	}
	.search:focus-within {
		border: 2px solid var(--primary);
		padding: 0 15px;
	}
	.search input {
		flex: 1;
		min-width: 0;
		border: 0;
		outline: none;
		background: transparent;
		color: var(--text);
		font-size: 1.0625rem;
		font-weight: 700;
	}
	.rows {
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 52px;
		padding: 0 16px;
		border-top: 1px solid var(--border);
		color: var(--text3);
	}
	.row:first-child {
		border-top: 0;
	}
	.name {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 0.9375rem;
		font-weight: 700;
		color: var(--text);
	}
	.code {
		font-size: 0.75rem;
		letter-spacing: 0.04em;
		color: var(--text3);
	}
	.line-h {
		display: flex;
		align-items: center;
		gap: 8px;
	}
</style>
