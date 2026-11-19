<script lang="ts">
	import { pfLabel, type Trip } from '#lib/data/queries.ts';
	import { lineStyle } from '#lib/lines.ts';
	import { href } from '#lib/nav.ts';
	import { prefs } from '#lib/state/prefs.svelte.ts';
	import KindTag from '#lib/ui/KindTag.svelte';
	import ReturnChip from '#lib/ui/ReturnChip.svelte';
	import { clock, daysLabel, duration } from '#lib/time.ts';

	let {
		trip,
		from,
		to,
		nowMinute,
		state
	}: { trip: Trip; from: string; to: string; nowMinute: number; state: 'departed' | 'next' | 'later' } = $props();

	const t = (m: number) => clock(m, prefs.h24);
	const color = $derived(state === 'departed' ? 'var(--text3)' : lineStyle(trip.line).color);
	const note = $derived(
		trip.operator === 'CR' ? 'Central Railway train' : daysLabel(trip.days, trip.notOnHolidays)
	);
	const inText = $derived.by(() => {
		if (state === 'departed') return '';
		if (trip.tomorrow) return 'Tomorrow';
		const m = trip.dep - nowMinute;
		const when = m <= 0 ? 'now' : `in ${duration(m)}`;
		return state === 'next' ? `Next · ${when}` : when;
	});
</script>

<a class="card" class:departed={state === 'departed'} class:next={state === 'next'} href={href.train(trip.trainId, from, to)}>
	<div class="times">
		<span class="time num">{t(trip.dep)}</span>
		<span class="track" aria-hidden="true" style:--c={color}>
			<span class="ring"></span><span class="rule"></span>
			<span class="dur num">{trip.minutes} min</span>
			<span class="rule"></span><span class="ring fill"></span>
		</span>
		<span class="time num">{t(trip.arr)}</span>
	</div>
	<div class="meta">
		<KindTag fast={trip.fast} ac={trip.ac} />
		<span class="dest">{trip.dest}</span>
		{#if trip.cars}<span aria-hidden="true">·</span><span>{trip.cars} car</span>{/if}
		{#if trip.pf}<span aria-hidden="true">·</span><span class="pf num">PF {pfLabel(trip.pf)}</span>{/if}
		{#if trip.ret && state !== 'departed'}<ReturnChip ret={trip.ret} {nowMinute} />{/if}
	</div>
	<div class="foot">
		<span class="status">
			{#if state === 'departed'}
				<span class="dot"></span>Departed
			{:else if note}
				<span class="dot warn"></span>{note}
			{:else}
				<span class="no num">No. {trip.number}</span>
			{/if}
		</span>
		<span class="in num">{inText}</span>
	</div>
</a>

<style>
	.card {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 14px 16px;
		border-radius: 20px;
		background: var(--surface);
		border: 1px solid var(--border);
	}
	.card.next {
		border: 2px solid var(--primary);
		padding: 13px 15px;
	}
	.card.departed {
		opacity: 0.55;
	}
	.times {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.time {
		font-size: 1.375rem;
		font-weight: 800;
		letter-spacing: -0.015em;
	}
	.track {
		flex: 1;
		display: flex;
		align-items: center;
		min-width: 24px;
	}
	.ring {
		flex: none;
		width: 11px;
		height: 11px;
		border-radius: 999px;
		border: 2px solid var(--c);
	}
	.ring.fill {
		background: var(--c);
	}
	.rule {
		flex: 1;
		height: 2px;
		background: var(--c);
	}
	.dur {
		padding: 0 8px;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--text3);
		white-space: nowrap;
	}
	.meta {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
		font-size: 0.8125rem;
		color: var(--text3);
	}
	.pf {
		font-weight: 700;
		color: var(--text2);
	}
	.dest {
		font-size: 0.9375rem;
		font-weight: 700;
		color: var(--text);
	}
	.foot {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding-top: 10px;
		border-top: 1px solid var(--border);
		font-size: 0.8125rem;
		font-weight: 700;
	}
	.status {
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--text3);
		min-width: 0;
	}
	.status .dot {
		flex: none;
		width: 8px;
		height: 8px;
		border-radius: 999px;
		background: var(--text3);
	}
	.status .dot.warn {
		background: var(--warn);
	}
	.no {
		font-weight: 600;
	}
	.in {
		color: var(--text2);
		white-space: nowrap;
	}
	.next .in {
		color: var(--primary);
	}
</style>
