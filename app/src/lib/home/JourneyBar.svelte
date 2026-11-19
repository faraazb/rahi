<script lang="ts">
	/** From / To with swap. Phone: docked above the tabs, slots stacked.
	 *  Wide: a single row under "Where to?", suggestions drop down from it. */
	import ArrowUpDown from '@lucide/svelte/icons/arrow-up-down';
	import ArrowLeftRight from '@lucide/svelte/icons/arrow-left-right';
	import X from '@lucide/svelte/icons/x';
	import type { Snippet } from 'svelte';
	import type { Station } from '#lib/data/queries.ts';
	import LineBadge from '#lib/ui/LineBadge.svelte';

	type Slot = 'from' | 'to';
	let {
		from,
		to,
		active,
		q = $bindable(''),
		wide = false,
		onopen,
		oncancel,
		onswap,
		onkeydown,
		dropdown
	}: {
		from: Station | null;
		to: Station | null;
		active: Slot | null;
		q?: string;
		wide?: boolean;
		onopen: (slot: Slot) => void;
		oncancel: () => void;
		onswap: () => void;
		onkeydown?: (e: KeyboardEvent) => void;
		dropdown?: Snippet;
	} = $props();

	const slots = $derived([
		{ id: 'from' as const, label: 'From', value: from, empty: 'Choose a station' },
		{ id: 'to' as const, label: 'To', value: to, empty: 'Where to?' }
	]);

	function focusOnMount(node: HTMLInputElement) {
		node.focus();
	}
</script>

<section class="journey" class:wide aria-label="Journey">
	<div class="slots">
		{#each slots as sl (sl.id)}
			<div class="slot" style:order={wide && sl.id === 'to' ? 2 : 0}>
				{#if active === sl.id}
					<div class="field editing">
						<span class="dot {sl.id}" class:filled={sl.id === 'to'} aria-hidden="true"></span>
						<span class="text">
							<label for="slot-{sl.id}" class="label on">{sl.label}</label>
							<input
								id="slot-{sl.id}"
								type="text"
								inputmode="search"
								autocomplete="off"
								autocapitalize="words"
								spellcheck="false"
								enterkeyhint="go"
								placeholder="Station or code"
								bind:value={q}
								{onkeydown}
								use:focusOnMount
							/>
						</span>
						<button type="button" class="cancel" aria-label="Cancel" onclick={oncancel}><X size={22} /></button>
					</div>
				{:else}
					<button type="button" class="field" onclick={() => onopen(sl.id)}>
						<span class="dot {sl.id}" class:filled={sl.id === 'to' && !!sl.value} aria-hidden="true"></span>
						<span class="text">
							<span class="label">{sl.label}</span>
							<span class="value" class:empty={!sl.value}>{sl.value?.name ?? sl.empty}</span>
						</span>
						<span class="badges">
							{#each sl.value?.lines ?? [] as line (line)}<LineBadge {line} size="lg" />{/each}
						</span>
					</button>
				{/if}
			</div>
		{/each}
		<button type="button" class="swap" aria-label="Swap stations" onclick={onswap}>
			{#if wide}<ArrowLeftRight size={20} />{:else}<ArrowUpDown size={22} />{/if}
		</button>
	</div>
	{@render dropdown?.()}
</section>

<style>
	.journey {
		flex: none;
		position: relative;
		margin: 0 12px 12px;
	}
	.slots {
		display: flex;
		flex-wrap: wrap;
		align-items: stretch;
		gap: 2px 4px;
		padding: 6px;
		border-radius: 26px;
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow);
		position: relative;
	}
	.journey:not(.wide) .slots {
		flex-direction: column;
		padding-right: 62px;
	}
	.slot {
		min-width: 0;
		display: flex;
	}
	.wide .slot {
		flex: 1 1 300px;
	}
	.field {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		gap: 12px;
		min-height: 62px;
		padding: 6px 6px 6px 14px;
		border: 2px solid transparent;
		border-radius: 20px;
		background: transparent;
		text-align: left;
	}
	.wide .field {
		height: 68px;
		gap: 14px;
		padding: 0 6px 0 18px;
		border-radius: 22px;
	}
	.field.editing {
		border-color: var(--primary);
		background: var(--surface);
	}
	.dot {
		flex: none;
		width: 14px;
		height: 14px;
		border-radius: 999px;
		background: var(--surface);
		border: 3px solid var(--text2);
	}
	.dot.to {
		border-color: var(--primary);
	}
	.dot.to.filled {
		background: var(--primary);
	}
	.text {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.label {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text3);
	}
	.label.on {
		color: var(--primary);
	}
	.value,
	input {
		height: 1.5625rem;
		font-size: 1.1875rem;
		line-height: 1.5625rem;
		font-weight: 800;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.wide .value,
	.wide input {
		height: 1.625rem;
		font-size: 1.25rem;
		line-height: 1.625rem;
	}
	.value.empty {
		font-weight: 600;
		color: var(--text3);
	}
	input {
		display: block;
		width: 100%;
		min-width: 0;
		margin: 0;
		padding: 0;
		border: 0;
		outline: none;
		background: transparent;
	}
	input::placeholder {
		color: var(--text3);
		font-weight: 600;
	}
	.badges {
		flex: none;
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 4px;
		min-width: 44px;
		height: 44px;
	}
	.cancel {
		flex: none;
		width: 44px;
		height: 44px;
		display: grid;
		place-items: center;
		border: 0;
		border-radius: 999px;
		background: transparent;
		color: var(--text3);
	}
	.swap {
		flex: none;
		align-self: center;
		width: 48px;
		height: 48px;
		display: grid;
		place-items: center;
		border-radius: 999px;
		border: 1px solid var(--border);
		background: var(--surface2);
		color: var(--text);
		order: 1;
	}
	.journey:not(.wide) .swap {
		position: absolute;
		right: 8px;
		top: 50%;
		margin-top: -24px;
	}
	.wide {
		margin: 0;
		width: 100%;
	}
	.wide .slots {
		border-radius: 28px;
	}
</style>
