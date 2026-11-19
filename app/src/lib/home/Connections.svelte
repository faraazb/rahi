<script lang="ts">
	/** Journeys with changes, for station pairs no single train serves. Each
	 *  card opens into a timeline of trains and changes. Change times are our
	 *  own minimums (planner.ts); no source gives walking routes, so a walk
	 *  says only where to, never which bridge. */
	import ArrowLeftRight from '@lucide/svelte/icons/arrow-left-right';
	import ArrowRight from '@lucide/svelte/icons/arrow-right';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Footprints from '@lucide/svelte/icons/footprints';
	import type { Journey, Leg } from '#lib/data/planner.ts';
	import { pfLabel } from '#lib/data/queries.ts';
	import { lineStyle } from '#lib/lines.ts';
	import { href } from '#lib/nav.ts';
	import { prefs } from '#lib/state/prefs.svelte.ts';
	import LineBadge from '#lib/ui/LineBadge.svelte';
	import { clock, duration } from '#lib/time.ts';

	let { journeys, nowMinute, heading = true }: { journeys: Journey[]; nowMinute: number; heading?: boolean } = $props();

	let open = $state(0);
	const t = (m: number) => clock(m, prefs.h24);
	const kind = (l: Leg) => `${l.fast ? 'Fast' : 'Slow'}${l.ac ? ' AC' : ''}`;
	const changeAt = (j: Journey) => [...new Set(j.legs.slice(0, -1).map((l) => l.toName))];

	const summary = $derived.by(() => {
		const j = journeys[0];
		if (!j) return '';
		const n = j.legs.length - 1;
		const at = changeAt(j);
		if (n === 0) return 'Walk between stations';
		return `${n} ${n === 1 ? 'change' : 'changes'} at ${at.join(', ')}`;
	});
	const firstArr = $derived(Math.min(...journeys.map((j) => j.arr)));
	const fewest = $derived(Math.min(...journeys.map((j) => j.legs.length)));

	type Tone = 'ok' | 'warn' | 'info';
	function tag(j: Journey): { text: string; tone: Tone } | null {
		if (j.changes.some((c) => c.tight)) return { text: 'Tight change', tone: 'warn' };
		if (journeys.length > 1 && j.arr === firstArr) return { text: 'Arrives first', tone: 'ok' };
		if (j.legs.length === fewest && journeys.some((o) => o.legs.length > fewest)) return { text: 'Fewer changes', tone: 'ok' };
		const ac = j.legs.findIndex((l) => l.ac);
		if (ac >= 0) return { text: j.legs.length === 1 ? 'AC' : `AC ${['first', 'second', 'third', 'fourth'][ac]} leg`, tone: 'info' };
		return null;
	}
	const leaves = (j: Journey) => {
		if (j.tomorrow) return 'tomorrow';
		const m = j.dep - nowMinute;
		return m <= 0 ? 'now' : `in ${duration(m)}`;
	};
	function legText(l: Leg): string {
		return [`${kind(l)} towards ${l.towards}`, l.cars ? `${l.cars} car` : null, `${l.arr - l.dep} min`].filter(Boolean).join(' · ');
	}
</script>

{#if heading && summary}
	<p class="summary"><ArrowLeftRight size={14} strokeWidth={2.4} aria-hidden="true" />{summary}</p>
{/if}

{#each journeys as j, i (j.legs.map((l) => l.trainId).join('-') + ':' + j.dep)}
	{@const tg = tag(j)}
	{@const last = j.legs.at(-1)!}
	<div class="card" class:open={open === i}>
		<button type="button" class="head" aria-expanded={open === i} onclick={() => (open = open === i ? -1 : i)}>
			<span class="top">
				<span class="time num">{t(j.dep)}</span>
				<ArrowRight size={16} strokeWidth={2.4} aria-hidden="true" />
				<span class="time num">{t(j.arr)}</span>
				<span class="total num">{duration(j.minutes)}</span>
				{#if tg}<span class="tag {tg.tone}">{tg.text}</span>{/if}
			</span>
			<span class="bar" aria-hidden="true">
				{#if j.walkStart}<span class="gap" style:flex={j.walkStart}></span>{/if}
				{#each j.legs as l, k (k)}
					<span class="seg" style:flex={l.arr - l.dep} style:background={lineStyle(l.line).color}></span>
					{#if j.changes[k]}<span class="gap" style:flex={Math.max(j.changes[k].minutes, 1)}></span>{/if}
				{/each}
				{#if j.walkEnd}<span class="gap" style:flex={j.walkEnd}></span>{/if}
			</span>
			<span class="legs">
				{#each j.legs as l, k (k)}
					{#if k > 0}
						<span aria-hidden="true">·</span>
						<span class="chg" class:tight={j.changes[k - 1].tight}>{j.changes[k - 1].minutes} min change</span>
						<span aria-hidden="true">·</span>
					{/if}
					<LineBadge line={l.line} /><span>{kind(l)}</span>
				{/each}
				<span class="leaves num">{leaves(j)}</span>
			</span>
		</button>

		{#if open === i}
			<ol class="steps">
				{#if j.walkStart}
					<li>
						<span class="at num">{t(j.dep)}</span>
						<span class="rail" aria-hidden="true"><span class="dot hollow" style:--c="var(--text3)"></span><span class="dots"></span></span>
						<span class="body">
							<span class="stn">{j.legs[0].fromName}</span>
							<span class="walk"><Footprints size={18} aria-hidden="true" /><span class="wtxt"><strong>{j.walkStart} min walk</strong><span>To the <LineBadge line={j.legs[0].line} size="sm" /> platforms</span></span></span>
						</span>
					</li>
				{/if}
				{#each j.legs as l, k (k)}
					{@const c = lineStyle(l.line).color}
					{@const chg = j.changes[k]}
					<li>
						<span class="at num">{t(l.dep)}</span>
						<span class="rail" aria-hidden="true"><span class="dot hollow" style:--c={c}></span><span class="line" style:background={c}></span></span>
						<span class="body">
							<span class="stn">{l.fromName}{#if l.pfFrom}&nbsp;· PF {pfLabel(l.pfFrom)}{/if}</span>
							<a class="legdesc" href={href.train(l.trainId, l.fromCode, l.toCode)}>{legText(l)}<ChevronRight size={14} strokeWidth={2.4} /></a>
						</span>
					</li>
					{#if chg}
						<li>
							<span class="at num">{t(l.arr)}</span>
							<span class="rail" aria-hidden="true"><span class="dot" style:--c={c}></span><span class="dots"></span></span>
							<span class="body roomy">
								<span class="stn">{l.toName}{#if l.pfTo}&nbsp;· get off at PF {pfLabel(l.pfTo)}{/if}</span>
								<span class="walk" class:tight={chg.tight}>
									<Footprints size={18} aria-hidden="true" />
									<span class="wtxt">
										<strong>{chg.minutes} min to change</strong>
										{#if chg.walk}<span>Walk to the <LineBadge line={chg.walk.toLine} size="sm" /> platforms at {chg.walk.toName}</span>
										{:else if chg.tight}<span>Little time to spare</span>{/if}
									</span>
								</span>
							</span>
						</li>
					{/if}
				{/each}
				{#if j.walkEnd}
					<li>
						<span class="at num">{t(last.arr)}</span>
						<span class="rail" aria-hidden="true"><span class="dot" style:--c={lineStyle(last.line).color}></span><span class="dots"></span></span>
						<span class="body roomy">
							<span class="stn">{last.toName}{#if last.pfTo}&nbsp;· get off at PF {pfLabel(last.pfTo)}{/if}</span>
							<span class="walk"><Footprints size={18} aria-hidden="true" /><span class="wtxt"><strong>{j.walkEnd} min walk</strong></span></span>
						</span>
					</li>
				{/if}
				<li>
					<span class="at num">{t(j.arr)}</span>
					<span class="rail end" aria-hidden="true"><span class="dot" style:--c={lineStyle(last.line).color}></span></span>
					<span class="stn">{j.walkEnd ? 'Arrive' : last.toName}</span>
				</li>
			</ol>
			<a class="track" href={href.train(j.legs[0].trainId, j.legs[0].fromCode, j.legs[0].toCode)}>
				First train<ChevronRight size={16} strokeWidth={2.4} />
			</a>
		{/if}
	</div>
{/each}

<style>
	.summary {
		display: flex;
		align-items: center;
		gap: 6px;
		margin: -4px 4px 0;
		justify-content: flex-end;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--text2);
	}
	.card {
		display: flex;
		flex-direction: column;
		border-radius: 20px;
		background: var(--surface);
		border: 1px solid var(--border);
		overflow: hidden;
	}
	.card.open {
		border: 2px solid var(--primary);
	}
	.head {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 14px 16px;
		border: 0;
		background: transparent;
		text-align: left;
	}
	.card.open .head {
		padding: 13px 15px;
	}
	.top {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
	}
	.time {
		font-size: 1.25rem;
		font-weight: 800;
		letter-spacing: -0.01em;
	}
	.total {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text3);
	}
	.tag {
		margin-left: auto;
		padding: 3px 8px;
		border-radius: 999px;
		font-size: 0.6875rem;
		font-weight: 800;
		white-space: nowrap;
	}
	.tag.ok {
		background: var(--success-soft);
		color: var(--success);
	}
	.tag.warn {
		background: var(--warn-soft);
		color: var(--warn);
	}
	.tag.info {
		background: var(--primary-soft);
		color: var(--on-primary-soft);
	}
	.bar {
		display: flex;
		align-items: center;
		gap: 3px;
		width: 100%;
		height: 8px;
	}
	.seg {
		height: 8px;
		border-radius: 999px;
		min-width: 6px;
	}
	.gap {
		height: 2px;
		border-top: 2px dotted var(--text3);
		min-width: 6px;
	}
	.legs {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
		width: 100%;
		font-size: 0.8125rem;
		color: var(--text3);
	}
	.chg {
		font-weight: 700;
		color: var(--text2);
	}
	.chg.tight {
		color: var(--warn);
	}
	.leaves {
		margin-left: auto;
		font-weight: 700;
		color: var(--text2);
	}

	.steps {
		list-style: none;
		margin: 0;
		padding: 4px 16px 14px;
		display: flex;
		flex-direction: column;
		border-top: 1px solid var(--border);
	}
	.steps li {
		display: flex;
		gap: 12px;
	}
	.steps li:first-child {
		padding-top: 12px;
	}
	.at {
		flex: none;
		width: 48px;
		text-align: right;
		font-size: 0.875rem;
		font-weight: 800;
	}
	.rail {
		flex: none;
		width: 14px;
		display: flex;
		flex-direction: column;
		align-items: center;
	}
	.rail.end {
		justify-content: flex-start;
	}
	.dot {
		flex: none;
		width: 12px;
		height: 12px;
		border-radius: 999px;
		background: var(--c);
	}
	.dot.hollow {
		border: 3px solid var(--c);
		background: var(--surface);
	}
	.line {
		flex: 1;
		width: 4px;
	}
	.dots {
		flex: 1;
		width: 0;
		border-left: 3px dotted var(--text3);
	}
	.body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding-bottom: 14px;
	}
	.body.roomy {
		gap: 8px;
	}
	.stn {
		font-size: 0.9375rem;
		font-weight: 800;
	}
	.legdesc {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		font-size: 0.8125rem;
		color: var(--text2);
	}
	.walk {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 12px;
		border-radius: 12px;
		background: var(--surface2);
		color: var(--text2);
	}
	.walk.tight {
		background: var(--warn-soft);
		color: var(--warn);
	}
	.wtxt {
		display: flex;
		flex-direction: column;
		gap: 1px;
		font-size: 0.75rem;
		font-weight: 600;
	}
	.wtxt strong {
		font-size: 0.8125rem;
		font-weight: 800;
	}
	.wtxt span {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		flex-wrap: wrap;
	}
	.track {
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
</style>
