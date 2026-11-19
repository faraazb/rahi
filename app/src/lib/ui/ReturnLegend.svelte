<script lang="ts">
	/** Key for ReturnChip, shown above a list that carries any. */
	import Undo2 from '@lucide/svelte/icons/undo-2';
</script>

<span class="legend">
	<span class="ico" aria-hidden="true"><Undo2 size={13} strokeWidth={2.6} /></span>
	Return
</span>

<style>
	.legend {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 0.75rem;
		font-weight: 700;
		color: var(--on-primary-soft);
		white-space: nowrap;
	}
	.ico {
		width: 20px;
		height: 20px;
		display: grid;
		place-items: center;
		border-radius: 6px;
		background: var(--primary-soft);
	}
</style>
