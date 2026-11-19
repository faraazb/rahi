<script lang="ts">
	import ChevronLeft from '@lucide/svelte/icons/chevron-left';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import X from '@lucide/svelte/icons/x';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { stationByCode } from '#lib/data/queries.ts';
	import { href } from '#lib/nav.ts';
	import { saved } from '#lib/state/saved.svelte.ts';
	import LineBadge from '#lib/ui/LineBadge.svelte';

	const rows = $derived.by(() => {
		void timetable.revision;
		const db = timetable.db;
		return saved.stations.map((code) => ({ code, st: db ? stationByCode(db, code) : null }));
	});
</script>

<div class="page">
	<header class="page-head">
		<div class="head-row">
			<a class="back" href={href.settings()} aria-label="Back"><ChevronLeft size={24} /></a>
			<div class="head-title"><h1>Saved stations</h1></div>
		</div>
	</header>
	<main class="page-main">
		{#if rows.length}
			<div class="card list">
				{#each rows as r (r.code)}
					<div class="row">
						<a href={href.station(r.code)}>
							<span class="name">{r.st?.name ?? r.code}</span>
							{#each r.st?.lines ?? [] as l (l)}<LineBadge line={l} />{/each}
							<ChevronRight size={18} />
						</a>
						<button type="button" aria-label="Remove {r.st?.name ?? r.code}" onclick={() => saved.toggleStation(r.code)}><X size={18} /></button>
					</div>
				{/each}
			</div>
		{:else}
			<p class="empty">No saved stations. Open a station from the Trains tab and tap the star to keep it here.</p>
		{/if}
	</main>
</div>

<style>
	.list {
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.row {
		display: flex;
		align-items: center;
		border-top: 1px solid var(--border);
	}
	.row:first-child {
		border-top: 0;
	}
	.row a {
		flex: 1;
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 56px;
		padding: 0 8px 0 16px;
		color: var(--text3);
	}
	.name {
		flex: 1;
		font-weight: 700;
		color: var(--text);
	}
	.row button {
		flex: none;
		width: 48px;
		height: 48px;
		display: grid;
		place-items: center;
		border: 0;
		background: transparent;
		color: var(--text3);
	}
	.empty {
		padding: 16px;
		border-radius: 20px;
		border: 1px dashed var(--border);
		color: var(--text2);
	}
</style>
