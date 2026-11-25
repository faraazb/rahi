<script lang="ts">
	/** The next few trains for the chosen route. Live status is not in any
	 *  source, so the pill shows the scheduled arrival instead. Platforms
	 *  appear only when the timetable carries them (local builds), and so does
	 *  the return chip (board the same train earlier, before it turns). */
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import { pfLabel, type Trip } from '#lib/data/queries.ts';
	import { href } from '#lib/nav.ts';
	import { prefs } from '#lib/state/prefs.svelte.ts';
	import KindTag from '#lib/ui/KindTag.svelte';
	import ReturnChip from '#lib/ui/ReturnChip.svelte';
	import ReturnLegend from '#lib/ui/ReturnLegend.svelte';
	import { clock } from '#lib/time.ts';

	let {
		trips,
		nowMinute,
		from,
		to,
		wide = false
	}: { trips: Trip[]; nowMinute: number; from: string; to: string; wide?: boolean } = $props();

	const t = (m: number) => clock(m, prefs.h24);
	const showPf = $derived(trips.some((x) => x.pf));
	const showRet = $derived(trips.some((x) => x.ret));
	const leaves = (trip: Trip) => {
		const m = trip.dep - nowMinute;
		if (trip.tomorrow) return 'tomorrow';
		if (m <= 0) return 'now';
		return m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
	};
</script>

{#if showRet}<div class="legend-row"><ReturnLegend /></div>{/if}
{#if wide}
	<div class="table card" class:with-pf={showPf} role="table" aria-label="Next trains">
		<div class="tr th" role="row">
			<span role="columnheader">Departs</span><span role="columnheader">Leaves in</span><span role="columnheader">Train</span><span role="columnheader">Journey</span>{#if showPf}<span role="columnheader">Platform</span>{/if}<span role="columnheader">Arrives</span><span></span>
		</div>
		{#each trips as trip, i (trip.trainId + ':' + trip.dep)}
			<a class="tr" role="row" href={href.train(trip.trainId, from, to)}>
				<span class="time num" role="cell">{t(trip.dep)}</span>
				<span class="leaves num" class:first={i === 0} role="cell">{leaves(trip)}</span>
				<span class="train" role="cell"><KindTag fast={trip.fast} ac={trip.ac} /><span class="dest">{trip.dest}</span>{#if trip.ret}<ReturnChip ret={trip.ret} {nowMinute} {from} />{/if}</span>
				<span class="dim num" role="cell">{trip.minutes} min</span>
				{#if showPf}<span role="cell">{#if trip.pf}<span class="pfbox num" aria-label="Platform {pfLabel(trip.pf)}">{pfLabel(trip.pf)}</span>{/if}</span>{/if}
				<span role="cell"><span class="arr num">{t(trip.arr)}</span></span>
				<span class="chev"><ChevronRight size={18} /></span>
			</a>
		{/each}
		<a class="all" href={href.trains(from, to)}>All trains today<ChevronRight size={16} strokeWidth={2.4} /></a>
	</div>
{:else}
	<div class="list card">
		{#each trips as trip, i (trip.trainId + ':' + trip.dep)}
			<a class="row" href={href.train(trip.trainId, from, to)}>
				<span class="when">
					<span class="time num">{t(trip.dep)}</span>
					<span class="in num" class:first={i === 0}>{trip.tomorrow ? 'tomorrow' : `in ${leaves(trip)}`}</span>
				</span>
				<span class="mid-col">
					<span class="mid">
						<KindTag fast={trip.fast} ac={trip.ac} />
						{#if showRet}
							<!-- Design D: destination first, the journey time is in the arrival pill. -->
							<span class="dest strong">{trip.dest}</span>
							{#if trip.pf}<span aria-hidden="true">·</span><span class="num pf">PF {pfLabel(trip.pf)}</span>{/if}
						{:else}
							<span class="num">{trip.minutes} min</span>
							{#if trip.pf}<span aria-hidden="true">·</span><span class="num pf">PF {pfLabel(trip.pf)}</span>{/if}
							<span aria-hidden="true">·</span><span class="dest">{trip.dest}</span>
						{/if}
					</span>
					{#if trip.ret}<ReturnChip ret={trip.ret} {nowMinute} {from} />{/if}
				</span>
				<span class="arr num" title="Scheduled arrival">arr {t(trip.arr)}</span>
			</a>
		{/each}
		<a class="all" href={href.trains(from, to)}>All trains today<ChevronRight size={16} strokeWidth={2.4} /></a>
	</div>
{/if}

<style>
	.card {
		overflow: hidden;
		display: flex;
		flex-direction: column;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 14px;
		min-height: 66px;
		padding: 10px 16px;
		border-top: 1px solid var(--border);
	}
	.row:first-child {
		border-top-color: transparent;
	}
	.when {
		flex: none;
		width: 64px;
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.time {
		font-size: 1.25rem;
		font-weight: 800;
		letter-spacing: -0.01em;
	}
	.in {
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--text3);
	}
	.in.first,
	.leaves.first {
		color: var(--primary);
	}
	.legend-row {
		display: flex;
		justify-content: flex-end;
		margin: -4px 4px 0;
	}
	.mid-col {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 5px;
	}
	.mid {
		min-width: 0;
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 0.8125rem;
		color: var(--text3);
		white-space: nowrap;
	}
	.pf {
		font-weight: 700;
		color: var(--text2);
	}
	.dest {
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.dest.strong {
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text);
	}
	.arr {
		flex: none;
		padding: 4px 8px;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 700;
		background: var(--surface2);
		color: var(--text2);
	}
	.all {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		min-height: 48px;
		border-top: 1px solid var(--border);
		color: var(--primary);
		font-size: 0.875rem;
		font-weight: 700;
	}

	/* wide table */
	.tr {
		display: grid;
		grid-template-columns: 108px 108px minmax(0, 1fr) 108px 108px 24px;
		align-items: center;
		gap: 0 12px;
		min-height: 80px;
		padding: 0 20px;
		border-top: 1px solid var(--border);
		font-size: 0.9375rem;
	}
	.with-pf .tr {
		grid-template-columns: 108px 108px minmax(0, 1fr) 96px 80px 108px 24px;
	}
	.pfbox {
		width: 34px;
		height: 34px;
		display: grid;
		place-items: center;
		border-radius: 10px;
		background: var(--surface2);
		font-size: 0.9375rem;
		font-weight: 800;
	}
	a.tr:hover {
		background: var(--surface2);
	}
	.th {
		min-height: 0;
		padding-top: 12px;
		padding-bottom: 12px;
		border-top: 0;
		background: var(--surface2);
		font-size: 0.6875rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text3);
	}
	.tr .time {
		font-size: 1.25rem;
	}
	.leaves {
		font-weight: 700;
		color: var(--text2);
	}
	.train {
		display: flex;
		align-items: center;
		gap: 8px;
		font-weight: 600;
		min-width: 0;
	}
	.dim {
		color: var(--text3);
	}
	.tr .arr {
		font-size: 0.875rem;
		padding: 5px 10px;
	}
	.chev {
		color: var(--text3);
	}
</style>
