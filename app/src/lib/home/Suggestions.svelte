<script lang="ts">
	/** Station choices while typing. On a phone the best match is drawn last,
	 *  closest to the thumb and the docked field (as in the design); on wide
	 *  screens it comes first, under the field, with arrow-key selection. */
	import MapPin from '@lucide/svelte/icons/map-pin';
	import type { Station } from '#lib/data/queries.ts';
	import LineBadge from '#lib/ui/LineBadge.svelte';

	let {
		items,
		title,
		q,
		highlight = 0,
		bestFirst = false,
		floating = false,
		side = 'left',
		onpick
	}: {
		items: Station[];
		title: string;
		q: string;
		highlight?: number;
		bestFirst?: boolean;
		floating?: boolean;
		side?: 'left' | 'right';
		onpick: (code: string) => void;
	} = $props();

	const ordered = $derived(bestFirst ? items : [...items].reverse());
	const highlighted = $derived(bestFirst ? highlight : items.length - 1 - highlight);
</script>

<section
	class="sugs"
	class:popover={floating}
	aria-label={title}
	style:left={floating && side === 'left' ? '0' : undefined}
	style:right={floating && side === 'right' ? '0' : undefined}
>
	<span class="eyebrow">{title}</span>
	<div class="list" role="listbox" aria-label={title}>
		{#each ordered as st, i (st.code)}
			<button
				type="button"
				role="option"
				aria-selected={!!q && i === highlighted}
				class:best={!!q && i === highlighted}
				onclick={() => onpick(st.code)}
			>
				<span class="pin"><MapPin size={20} /></span>
				<span class="name">
					<span class="row"><span class="n">{st.name}</span><span class="code">{st.code}</span></span>
					{#if q && i === highlighted}<span class="hint">Best match</span>{/if}
				</span>
				<span class="lines">{#each st.lines as line (line)}<LineBadge {line} size="lg" />{/each}</span>
			</button>
		{:else}
			{#if q}
				<p class="empty">No station matches “{q}”. Try its code, like DDR for Dadar.</p>
			{:else}
				<p class="empty">Type a station name or its code, like Dadar or DDR.</p>
			{/if}
		{/each}
	</div>
	{#if floating}
		<div class="keys"><kbd>Enter</kbd> pick top match <kbd>Esc</kbd> cancel</div>
	{/if}
</section>

<style>
	.sugs {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.list {
		display: flex;
		flex-direction: column;
		border-radius: 20px;
		background: var(--surface);
		border: 1px solid var(--border);
		overflow: hidden;
	}
	button {
		display: flex;
		align-items: center;
		gap: 14px;
		min-height: 60px;
		padding: 8px 16px;
		border: 0;
		border-top: 1px solid var(--border);
		background: transparent;
		text-align: left;
	}
	button:first-child {
		border-top-color: transparent;
	}
	button.best {
		background: var(--primary-soft);
	}
	.pin {
		flex: none;
		width: 36px;
		height: 36px;
		display: grid;
		place-items: center;
		border-radius: 12px;
		background: var(--surface2);
		color: var(--text3);
	}
	.name {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.n {
		font-size: 1rem;
		font-weight: 700;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.code {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		color: var(--text3);
	}
	.hint {
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--primary);
	}
	.lines {
		flex: none;
		display: flex;
		gap: 4px;
	}
	.empty {
		padding: 18px 16px;
		font-size: 0.875rem;
		color: var(--text3);
	}

	.popover {
		position: absolute;
		z-index: 5;
		top: calc(100% + 8px);
		width: min(460px, 100%);
		gap: 0;
		border-radius: 20px;
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow-pop);
		overflow: hidden;
	}
	.popover .eyebrow {
		margin: 0;
		padding: 12px 16px 6px;
		font-size: 0.75rem;
	}
	.popover .list {
		border: 0;
		border-radius: 0;
		max-height: min(60vh, 420px);
		overflow-y: auto;
	}
	.popover button {
		min-height: 56px;
	}
	.keys {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 16px;
		border-top: 1px solid var(--border);
		background: var(--surface2);
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--text3);
	}
	kbd {
		padding: 1px 6px;
		border-radius: 5px;
		border: 1px solid var(--border);
		background: var(--surface);
		font: inherit;
		font-weight: 700;
		color: var(--text2);
	}
	kbd:not(:first-child) {
		margin-left: 8px;
	}
</style>
