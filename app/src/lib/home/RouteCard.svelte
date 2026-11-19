<script lang="ts">
	import ArrowRight from '@lucide/svelte/icons/arrow-right';
	import { pfLabel, type Station, type Trip } from '#lib/data/queries.ts';
	import { prefs } from '#lib/state/prefs.svelte.ts';
	import { clock } from '#lib/time.ts';

	let {
		from,
		to,
		trips,
		nowMinute,
		usual = false,
		wide = false,
		onclick
	}: {
		from: Station;
		to: Station;
		trips: Trip[];
		nowMinute: number;
		usual?: boolean;
		wide?: boolean;
		onclick: () => void;
	} = $props();

	const next = $derived(trips[0]);
	const inMin = $derived(next && !next.tomorrow ? next.dep - nowMinute : null);
	const t = (m: number) => clock(m, prefs.h24);
	const then = $derived(trips.slice(1, 3).filter((x) => !x.tomorrow).map((x) => t(x.dep)));
</script>

<button type="button" class="route" class:usual class:wide {onclick}>
	<span class="body">
		{#if usual && !wide}<span class="tag">Usual at this hour</span>{/if}
		<span class="title">
			<span class="names">{from.name}<ArrowRight size={16} strokeWidth={2.4} />{to.name}</span>
			{#if usual && wide}<span class="tag">Usual now</span>{/if}
		</span>
		<span class="meta num">
			{#if !next}
				No direct trains
			{:else if next.tomorrow}
				No more trains today · first {t(next.dep)}
			{:else}
				<span class="strong">Next {t(next.dep)} {next.fast ? 'fast' : 'slow'}{next.ac ? ' AC' : ''}{next.pf ? ` · PF ${pfLabel(next.pf)}` : ''}</span>{#if wide}<br />{:else}{' · '}{/if}{then.length ? `then ${then.join(', ')}` : 'last train tonight'}
			{/if}
		</span>
	</span>
	{#if inMin !== null}
		<span class="in num">
			{#if inMin < 100}
				<span class="big">{inMin}</span><span class="unit">min</span>
			{:else}
				<span class="big small">{t(next.dep)}</span><span class="unit">next</span>
			{/if}
		</span>
	{/if}
</button>

<style>
	.route {
		display: flex;
		align-items: center;
		gap: 12px;
		min-height: 84px;
		padding: 14px 16px;
		border-radius: 20px;
		border: 1px solid var(--border);
		background: var(--surface);
		text-align: left;
		width: 100%;
	}
	.route.usual {
		border: 2px solid var(--primary);
		padding: 13px 15px;
	}
	.body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.tag {
		align-self: flex-start;
		padding: 2px 8px;
		border-radius: 999px;
		font-size: 0.6875rem;
		font-weight: 800;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		background: var(--primary-soft);
		color: var(--on-primary-soft);
		white-space: nowrap;
	}
	.title {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}
	.names {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 1.0625rem;
		font-weight: 800;
		letter-spacing: -0.01em;
		min-width: 0;
		overflow: hidden;
		white-space: nowrap;
	}
	.names :global(svg) {
		flex: none;
		color: var(--text2);
	}
	.meta {
		font-size: 0.8125rem;
		color: var(--text3);
	}
	.in {
		flex: none;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
	}
	.big {
		font-size: 1.75rem;
		line-height: 1;
		font-weight: 800;
		letter-spacing: -0.02em;
	}
	.big.small {
		font-size: 1.25rem;
	}
	.usual .big {
		color: var(--primary);
	}
	.unit {
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--text3);
	}

	/* Wide: a tile in a three-column grid, meta at the bottom. */
	.wide {
		align-items: flex-end;
		min-height: 132px;
		padding: 18px;
	}
	.wide.usual {
		padding: 17px;
	}
	.wide .body {
		align-self: stretch;
		justify-content: space-between;
	}
	.wide .strong {
		color: var(--text);
		font-weight: 700;
	}
	.wide .in {
		flex-direction: row;
		align-items: baseline;
		gap: 3px;
	}
</style>
