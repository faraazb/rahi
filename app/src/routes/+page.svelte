<script lang="ts">
	import Star from '@lucide/svelte/icons/star';
	import { untrack } from 'svelte';
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { upcomingJourneys } from '#lib/data/planner.ts';
	import { searchStations, stationByCode, stations, upcomingTrips, withReturns, type Station } from '#lib/data/queries.ts';
	import Connections from '#lib/home/Connections.svelte';
	import JourneyBar from '#lib/home/JourneyBar.svelte';
	import NextTrains from '#lib/home/NextTrains.svelte';
	import RouteCard from '#lib/home/RouteCard.svelte';
	import Suggestions from '#lib/home/Suggestions.svelte';
	import { clock, media } from '#lib/state/clock.svelte.ts';
	import { routeKey, saved, type Route } from '#lib/state/saved.svelte.ts';

	type Slot = 'from' | 'to';

	const db = $derived.by(() => {
		void timetable.revision;
		return timetable.db!;
	});
	const find = (code: string | null) => (code ? stationByCode(db, code) : null);

	// Deep links: /?from=DDR&to=BVI
	let fromCode = $state<string | null>(page.url.searchParams.get('from'));
	let toCode = $state<string | null>(page.url.searchParams.get('to'));
	let active = $state<Slot | null>(null);
	let q = $state('');
	let highlight = $state(0);

	const from = $derived(find(fromCode));
	const to = $derived(find(toCode));
	const picking = $derived(active !== null);
	const results = $derived(!picking && !!from && !!to);

	// ---- station suggestions
	const other = $derived(active === 'from' ? toCode : fromCode);
	const matches = $derived.by((): Station[] => {
		if (!picking) return [];
		if (q.trim()) return searchStations(db, q, other, media.wide ? 6 : 5);
		const codes = [...new Set([...saved.recent, ...saved.stations])].filter((c) => c !== other);
		return codes.map(find).filter((s): s is Station => !!s).slice(0, 6);
	});
	$effect(() => {
		void q;
		highlight = 0;
	});

	function open(slot: Slot) {
		active = slot;
		q = '';
	}
	function cancel() {
		active = null;
		q = '';
	}
	function pick(code: string) {
		saved.picked(code);
		if (active === 'from') {
			fromCode = code;
			active = toCode ? null : 'to';
		} else {
			toCode = code;
			active = fromCode ? null : 'from';
		}
		q = '';
	}
	function swap() {
		[fromCode, toCode] = [toCode, fromCode];
	}
	function onkeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') cancel();
		else if (e.key === 'Enter' && matches[highlight]) pick(matches[highlight].code);
		else if (e.key === 'ArrowDown' && media.wide) {
			highlight = Math.min(highlight + 1, matches.length - 1);
			e.preventDefault();
		} else if (e.key === 'ArrowUp' && media.wide) {
			highlight = Math.max(highlight - 1, 0);
			e.preventDefault();
		}
	}

	// ---- results
	const trips = $derived(results ? withReturns(db, upcomingTrips(db, from!, to!, clock.now, 4), from!, clock.now.dow) : []);
	// No single train between them: journeys with changes instead.
	const journeys = $derived(results && !trips.length ? upcomingJourneys(db, fromCode!, toCode!, clock.now, 3) : []);
	const route = $derived<Route | null>(results ? { from: fromCode!, to: toCode! } : null);
	const pinned = $derived(route ? saved.isPinned(route) : false);

	// Keep the URL shareable and learn which routes are used at which hour.
	// Only `route` is tracked; the writes below must not re-trigger this.
	let lastRecorded = '';
	$effect(() => {
		const r = route;
		if (!r) return;
		untrack(() => {
			const k = routeKey(r);
			if (k === lastRecorded) return;
			lastRecorded = k;
			const url = new URL(page.url.href);
			url.searchParams.set('from', r.from);
			url.searchParams.set('to', r.to);
			replaceState(url, {});
			saved.used(r, clock.hour);
		});
	});

	// ---- your routes
	const yourRoutes = $derived.by(() => {
		const list = [...saved.pinned];
		if (saved.last && !saved.isPinned(saved.last)) list.push(saved.last);
		return list
			.map((r) => ({ r, from: find(r.from), to: find(r.to) }))
			.filter((x): x is { r: Route; from: Station; to: Station } => !!x.from && !!x.to);
	});
	const usual = $derived(saved.usualAt(clock.hour, yourRoutes.map((x) => x.r)));
	const routeCards = $derived(
		yourRoutes
			.map((x) => ({
				...x,
				usual: !!usual && routeKey(usual) === routeKey(x.r),
				trips: upcomingTrips(db, x.from, x.to, clock.now, 3)
			}))
			.sort((a, b) => Number(b.usual) - Number(a.usual))
	);
	function go(r: Route) {
		fromCode = r.from;
		toCode = r.to;
		active = null;
	}
</script>

{#snippet pinButton()}
	<button
		type="button"
		class="pin"
		class:on={pinned}
		aria-pressed={pinned}
		onclick={() => route && saved.togglePin(route)}
	>
		<Star size={16} fill={pinned ? 'currentColor' : 'none'} />{pinned ? 'Pinned' : 'Pin route'}
	</button>
{/snippet}

{#snippet routesSection(wide: boolean)}
	{#if routeCards.length}
		<section class="routes" class:grid={wide} aria-labelledby="routes-h">
			<h2 id="routes-h" class="eyebrow">Your routes</h2>
			<div class="route-list">
				{#each routeCards as c (routeKey(c.r))}
					<RouteCard from={c.from} to={c.to} trips={c.trips} nowMinute={clock.now.minute} usual={c.usual} {wide} onclick={() => go(c.r)} />
				{/each}
			</div>
		</section>
	{:else}
		<p class="hello">
			Pick a <strong>From</strong> and <strong>To</strong> station to see the next trains. Pin a route and it stays
			here, with its next train counting down.
		</p>
	{/if}
{/snippet}

{#if media.wide}
	<main class="wide-home">
		<h1>Where to?</h1>
		<JourneyBar {from} {to} {active} bind:q wide onopen={open} oncancel={cancel} onswap={swap} {onkeydown}>
			{#snippet dropdown()}
				{#if picking}
					<Suggestions
						items={matches}
						title={q.trim() ? 'Matches' : 'Recent'}
						{q}
						{highlight}
						bestFirst
						floating
						side={active === 'to' ? 'right' : 'left'}
						onpick={pick}
					/>
				{/if}
			{/snippet}
		</JourneyBar>
		{#if results}
			<section class="results" aria-labelledby="res-h">
				<div class="res-head">
					<h2 id="res-h" class="eyebrow">Next trains · {from!.name} to {to!.name}</h2>
					{@render pinButton()}
				</div>
				{#if trips.length}
					<NextTrains {trips} nowMinute={clock.now.minute} from={fromCode!} to={toCode!} wide />
				{:else if journeys.length}
					<Connections {journeys} nowMinute={clock.now.minute} />
				{:else}
					<p class="hello">No trains between these stations.</p>
				{/if}
			</section>
		{:else}
			{@render routesSection(true)}
		{/if}
	</main>
{:else}
	<div class="page">
		<main class="page-main phone-home">
			<div class="spacer" aria-hidden="true"></div>
			{#if picking}
				<Suggestions items={matches} title={q.trim() ? 'Matches' : 'Recent'} {q} {highlight} onpick={pick} />
			{:else if results}
				<section class="results" aria-labelledby="res-h">
					<div class="res-head">
						<h2 id="res-h" class="eyebrow">Next trains</h2>
						{@render pinButton()}
					</div>
					{#if trips.length}
						<NextTrains {trips} nowMinute={clock.now.minute} from={fromCode!} to={toCode!} />
					{:else if journeys.length}
						<Connections {journeys} nowMinute={clock.now.minute} />
					{:else}
						<p class="hello">No trains between these stations.</p>
					{/if}
				</section>
			{:else}
				{@render routesSection(false)}
			{/if}
		</main>
		<JourneyBar {from} {to} {active} bind:q onopen={open} oncancel={cancel} onswap={swap} {onkeydown} />
	</div>
{/if}

<style>
	.phone-home {
		padding-top: calc(env(safe-area-inset-top, 0px) + 24px);
		padding-bottom: 12px;
	}
	.spacer {
		flex: 1;
	}
	.routes,
	.results {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.route-list {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.res-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin: 0 4px;
	}
	.res-head .eyebrow {
		margin: 0;
	}
	.pin {
		display: flex;
		align-items: center;
		gap: 6px;
		height: 36px;
		padding: 0 12px;
		border-radius: 999px;
		border: 1px solid var(--border);
		background: var(--surface);
		color: var(--text2);
		font-size: 0.8125rem;
		font-weight: 700;
	}
	.pin.on {
		border-color: var(--primary-soft);
		background: var(--primary-soft);
		color: var(--on-primary-soft);
	}
	.hello {
		margin: 0 4px;
		padding: 16px;
		border-radius: 20px;
		border: 1px dashed var(--border);
		color: var(--text2);
		font-size: 0.9375rem;
		line-height: 1.45;
	}

	.wide-home {
		width: 100%;
		max-width: 928px;
		margin: 0 auto;
		padding: 88px 24px 64px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 40px;
	}
	.wide-home h1 {
		margin-bottom: -16px;
		font-size: 3rem;
		line-height: 1.05;
		font-weight: 800;
		letter-spacing: -0.03em;
		text-align: center;
	}
	.wide-home .routes,
	.wide-home .results,
	.wide-home .hello {
		width: 100%;
	}
	.routes.grid .route-list {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 12px;
	}
</style>
