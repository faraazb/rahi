<script lang="ts">
	/** FAST / SLOW, plus AC when the rake is air-conditioned that day. */
	let { fast, ac = false, size = 'md' }: { fast: boolean; ac?: boolean; size?: 'sm' | 'md' } = $props();
</script>

<span class="tags">
	<span class="tag {size}" class:fast>{fast ? 'FAST' : 'SLOW'}</span>
	{#if ac}<span class="tag {size} ac">AC</span>{/if}
</span>

<style>
	.tags {
		display: inline-flex;
		gap: 4px;
		flex: none;
	}
	.tag {
		padding: 1px 6px;
		border-radius: 6px;
		font-weight: 800;
		letter-spacing: 0.04em;
		background: var(--surface2);
		color: var(--text2);
		line-height: 1.45;
	}
	.md {
		font-size: 0.6875rem;
	}
	.sm {
		font-size: 0.625rem;
		border-radius: 5px;
	}
	.fast {
		background: var(--text);
		color: var(--surface);
	}
	.ac {
		background: var(--primary-soft);
		color: var(--on-primary-soft);
	}
</style>
