<script lang="ts">
	/** "↩ 18:07 · PF 3": the same train, caught earlier on its way into the
	 *  terminus where it turns. Board it there and stay on for a seat. Struck
	 *  through once that earlier train has left. Opens that train's page.
	 *  It sits inside a card's <a>, so it can't be one: the capture handler runs
	 *  before the card's link and SvelteKit's router (which skip a prevented click). */
	import Undo2 from '@lucide/svelte/icons/undo-2';
	import { goto } from '$app/navigation';
	import { pfLabel, type ReturnBoarding } from '#lib/data/queries.ts';
	import { href } from '#lib/nav.ts';
	import { prefs } from '#lib/state/prefs.svelte.ts';
	import { clock } from '#lib/time.ts';

	let { ret, nowMinute, from }: { ret: ReturnBoarding; nowMinute: number; from: string } = $props();

	const missed = $derived(ret.dep < nowMinute);
	const time = $derived(clock(ret.dep, prefs.h24));
	const pf = $derived(pfLabel(ret.pf));
	const label = $derived(
		`${missed ? 'Missed: ' : ''}board earlier at ${time}${pf ? ` from platform ${pf}` : ''}, going to ${ret.terminus || 'the terminus'}, and stay on`
	);

	// Its run ends where it turns, so the page shows your station to there.
	function open(e: Event) {
		e.preventDefault();
		e.stopPropagation();
		goto(href.train(ret.trainId, from));
	}
</script>

<span
	class="chip num"
	class:missed
	role="link"
	tabindex="0"
	aria-label={label}
	title={label}
	onclickcapture={open}
	onkeydowncapture={(e) => e.key === 'Enter' && open(e)}
>
	<Undo2 size={13} strokeWidth={2.6} aria-hidden="true" />
	<span class="txt">{time}{#if pf}&nbsp;· PF {pf}{/if}</span>
</span>

<style>
	.chip {
		flex: none;
		align-self: flex-start;
		display: inline-flex;
		align-items: center;
		gap: 5px;
		height: 22px;
		padding: 0 8px 0 6px;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 800;
		white-space: nowrap;
		background: var(--primary-soft);
		color: var(--on-primary-soft);
		cursor: pointer;
	}
	.missed {
		background: var(--surface2);
		color: var(--text3);
	}
	.missed .txt {
		text-decoration: line-through;
	}
</style>
