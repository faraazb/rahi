<script lang="ts">
	import { lineStyle } from '#lib/lines.ts';

	let { line, size = 'md' }: { line: string; size?: 'sm' | 'md' | 'lg' } = $props();
	const style = $derived(lineStyle(line));
</script>

<span class="badge {size}" style:background={style.color} title="{line} line">{style.badge}</span>

<style>
	.badge {
		flex: none;
		display: inline-grid;
		place-items: center;
		padding: 0 4px;
		border-radius: 6px;
		font-weight: 800;
		color: var(--on-line);
		line-height: 1;
	}
	.sm {
		min-width: 18px;
		height: 18px;
		border-radius: 5px;
		font-size: 0.625rem;
	}
	.md {
		min-width: 20px;
		height: 20px;
		font-size: 0.6875rem;
	}
	.lg {
		min-width: 22px;
		height: 22px;
		font-size: 0.6875rem;
	}
</style>
