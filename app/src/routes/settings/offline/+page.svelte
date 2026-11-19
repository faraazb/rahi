<script lang="ts">
	import Check from '@lucide/svelte/icons/check';
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import RefreshCw from '@lucide/svelte/icons/refresh-cw';
	import { DATA_MANIFEST_URL } from '#lib/config.ts';
	import { hasPlatforms } from '#lib/data/queries.ts';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { href } from '#lib/nav.ts';
	import LineBadge from '#lib/ui/LineBadge.svelte';
	import { longDate, relativeDate } from '#lib/time.ts';

	const m = $derived(timetable.manifest);
	const platforms = $derived.by(() => {
		void timetable.revision;
		return !!timetable.db && hasPlatforms(timetable.db);
	});
	const kb = (n: number) => `${Math.round(n / 1024)} KB`;
	const busy = $derived(timetable.update.state === 'checking' || timetable.update.state === 'downloading');
	const status = $derived.by(() => {
		const u = timetable.update;
		switch (u.state) {
			case 'checking':
				return 'Checking…';
			case 'downloading':
				return `Downloading ${kb(u.received)} of ${kb(u.total)}`;
			case 'current':
				return 'You have the latest timetable';
			case 'updated':
				return u.from ? 'Updated to the latest timetable' : 'Timetable downloaded';
			case 'offline':
				return "You're offline. The saved timetable keeps working.";
			case 'app-too-old':
				return 'A newer timetable needs a newer version of the app. Reload to update.';
			case 'failed':
				return `Couldn't update: ${u.message}`;
			default:
				return '';
		}
	});
	const ok = $derived(timetable.update.state === 'current' || timetable.update.state === 'updated');
</script>

<div class="page">
	<header class="page-head">
		<div class="head-row">
			<a class="back" href={href.settings()} aria-label="Back"><ChevronLeft size={24} /></a>
			<div class="head-title"><h1>Offline timetable</h1></div>
		</div>
	</header>
	<main class="page-main">
		{#if m}
			<section class="card block">
				<div class="kv"><span>Version</span><span class="num">{m.version}</span></div>
				<div class="kv"><span>Published</span><span>{relativeDate(m.published_at)}</span></div>
				<div class="kv"><span>Trains</span><span class="num">{m.counts.trains.toLocaleString('en-IN')}</span></div>
				<div class="kv"><span>Size on device</span><span class="num">{kb(m.db.raw_size)}</span></div>
				{#if platforms}<div class="kv"><span>Platforms</span><span>Yatri app · local build</span></div>{/if}
			</section>

			<h2 class="eyebrow">Lines</h2>
			<section class="card block">
				{#each m.lines as l (l.code)}
					<div class="line">
						<LineBadge line={l.code} size="lg" />
						<span class="text">
							<span class="label">{l.name} line</span>
							<span class="sub">
								{l.effective_from ? `Timetable in force from ${longDate(l.effective_from)}` : 'Effective date not recorded'} · {Object.keys(l.sources).length} official PDFs
							</span>
						</span>
					</div>
				{/each}
			</section>
		{:else}
			<p class="note">No timetable on this device yet.</p>
		{/if}

		<section class="card block">
			<button type="button" class="check" disabled={busy} onclick={() => timetable.check(true)}>
				<RefreshCw size={18} class={busy ? 'spin' : ''} />Check for updates
			</button>
			{#if status}
				<p class="status" class:ok>{#if ok}<Check size={16} />{/if}{status}</p>
			{/if}
		</section>

		<h2 class="eyebrow">Where the times come from</h2>
		<section class="card block prose">
			<p>
				Every time in this app comes from the railways' own published timetables: Western and Central Railway's
				suburban timetable PDFs, and Indian Railways' NTES for the Vasai–Diva–Panvel MEMUs and the Matheran hill
				railway. They are read by an open-source parser and checked before release. Nothing is crowdsourced or
				estimated.
			</p>
			{#if platforms}
				<p>
					These are <strong>scheduled</strong> times. Platform numbers and door sides in this build come from the
					database bundled in the Yatri app, matched to each train by number and time; no official source
					publishes them. This build is for local use only. Live running status is not shown.
				</p>
			{:else}
				<p>
					These are <strong>scheduled</strong> times. Platform numbers and live running status are not in any
					official source the app can use yet, so they are not shown.
				</p>
			{/if}
			<p class="mono">Updates from {DATA_MANIFEST_URL}</p>
		</section>
	</main>
</div>

<style>
	.block {
		display: flex;
		flex-direction: column;
		padding: 4px 16px;
	}
	.kv {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		min-height: 48px;
		align-items: center;
		border-top: 1px solid var(--border);
		font-size: 0.9375rem;
	}
	.kv:first-child {
		border-top: 0;
	}
	.kv span:first-child {
		color: var(--text3);
		font-weight: 600;
	}
	.kv span:last-child {
		font-weight: 700;
		text-align: right;
		overflow-wrap: anywhere;
	}
	.line {
		display: flex;
		align-items: center;
		gap: 12px;
		min-height: 64px;
	}
	.text {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.label {
		font-weight: 700;
	}
	.sub {
		font-size: 0.8125rem;
		color: var(--text3);
	}
	.check {
		margin: 12px 0;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		height: 48px;
		border-radius: 14px;
		border: 0;
		background: var(--primary);
		color: var(--on-primary);
		font-weight: 700;
	}
	.check:disabled {
		opacity: 0.6;
		cursor: default;
	}
	.check :global(.spin) {
		animation: spin 1s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.status {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		margin: -4px 0 12px;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text2);
		text-align: center;
	}
	.status.ok {
		color: var(--success);
	}
	.prose {
		gap: 10px;
		padding: 14px 16px;
		font-size: 0.875rem;
		line-height: 1.5;
		color: var(--text2);
	}
	.mono {
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
		color: var(--text3);
		overflow-wrap: anywhere;
	}
	.note {
		color: var(--text2);
		padding: 8px 4px;
	}
</style>
