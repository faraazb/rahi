<script lang="ts">
	/** Placeholder mark until the app has a real logo: a train-front glyph on
	 *  the brand colour (same artwork as static/icon.svg). */
	let { size = 28 }: { size?: number } = $props();
</script>

<svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
	<rect width="48" height="48" rx="12" fill="var(--primary)" />
	<g fill="none" stroke="var(--on-primary)" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">
		<rect x="15" y="10" width="18" height="22" rx="5" />
		<path d="M15 22h18M20 27h.01M28 27h.01M19 38l2.5-6M29 38l-2.5-6" />
	</g>
</svg>
