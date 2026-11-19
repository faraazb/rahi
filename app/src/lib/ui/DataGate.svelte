<script lang="ts">
	/** Shown until a timetable is on the device: first download, offline on
	 *  first launch, or a failed download. */
	import Download from '@lucide/svelte/icons/download';
	import WifiOff from '@lucide/svelte/icons/wifi-off';
	import CircleAlert from '@lucide/svelte/icons/circle-alert';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { APP_NAME } from '#lib/config.ts';

	const progress = $derived(
		timetable.update.state === 'downloading'
			? { received: timetable.update.received, total: timetable.update.total }
			: null
	);
	const kb = (n: number) => `${Math.round(n / 1024)} KB`;
</script>

<div class="gate">
	<div class="card">
		{#if timetable.status === 'missing'}
			<span class="icon warn"><WifiOff size={26} /></span>
			<h1>You're offline</h1>
			<p>
				{APP_NAME} needs to download the timetable once (about half a megabyte). After that it works without
				a connection.
			</p>
			<button type="button" class="primary" onclick={() => location.reload()}>Try again</button>
		{:else if timetable.status === 'error'}
			<span class="icon danger"><CircleAlert size={26} /></span>
			<h1>Couldn't get the timetable</h1>
			<p>{timetable.error ?? 'The download failed.'}</p>
			<button type="button" class="primary" onclick={() => location.reload()}>Try again</button>
		{:else}
			<span class="icon"><Download size={26} /></span>
			<h1>Getting the timetable</h1>
			<p>One download, then everything works offline.</p>
			<div class="bar" role="progressbar" aria-valuemin={0} aria-valuemax={progress?.total ?? 1} aria-valuenow={progress?.received ?? 0}>
				<span style:width={progress ? `${Math.min(100, (100 * progress.received) / progress.total)}%` : '8%'}></span>
			</div>
			<p class="num meta">{progress ? `${kb(progress.received)} of ${kb(progress.total)}` : 'Checking for the latest timetable…'}</p>
		{/if}
	</div>
</div>

<style>
	.gate {
		flex: 1;
		display: grid;
		place-items: center;
		padding: 24px 16px;
	}
	.card {
		width: min(420px, 100%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
		padding: 28px 24px;
		border-radius: 24px;
		background: var(--surface);
		border: 1px solid var(--border);
		box-shadow: var(--shadow);
		text-align: center;
	}
	.icon {
		width: 52px;
		height: 52px;
		display: grid;
		place-items: center;
		border-radius: 16px;
		background: var(--primary-soft);
		color: var(--on-primary-soft);
	}
	.icon.warn {
		background: var(--warn-soft);
		color: var(--warn);
	}
	.icon.danger {
		background: var(--danger-soft);
		color: var(--danger);
	}
	h1 {
		font-size: 1.1875rem;
		font-weight: 800;
	}
	p {
		color: var(--text2);
		font-size: 0.9375rem;
	}
	.meta {
		font-size: 0.8125rem;
		color: var(--text3);
	}
	.bar {
		width: 100%;
		height: 6px;
		border-radius: 999px;
		background: var(--surface2);
		overflow: hidden;
	}
	.bar span {
		display: block;
		height: 100%;
		border-radius: 999px;
		background: var(--primary);
		transition: width 0.2s;
	}
	.primary {
		margin-top: 4px;
		height: 48px;
		padding: 0 22px;
		border: 0;
		border-radius: 16px;
		background: var(--primary);
		color: var(--on-primary);
		font-weight: 700;
	}
</style>
