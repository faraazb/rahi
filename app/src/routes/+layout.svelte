<script lang="ts">
	import '@fontsource-variable/figtree';
	import '../app.css';
	import { page } from '$app/state';
	import { APP_NAME } from '#lib/config.ts';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { clock, media } from '#lib/state/clock.svelte.ts';
	import { prefs } from '#lib/state/prefs.svelte.ts';
	import { saved } from '#lib/state/saved.svelte.ts';
	import BottomNav from '#lib/ui/BottomNav.svelte';
	import DataGate from '#lib/ui/DataGate.svelte';
	import TopNav from '#lib/ui/TopNav.svelte';

	let { children } = $props();

	prefs.load();
	saved.load();
	media.start();
	clock.start();
	void timetable.start();

	$effect(() => {
		// Track every preference so any change re-applies and persists.
		void [prefs.theme, prefs.textSize, prefs.lineColours, prefs.h24];
		prefs.apply();
	});

	const routeId = $derived(page.route.id ?? '');
	// Settings work without a timetable; everything else needs one.
	const needsData = $derived(!routeId.startsWith('/settings'));
	// The train screen has its own action bar in place of the tabs.
	const showTabs = $derived(routeId !== '/train/[id]');
</script>

<svelte:head>
	<title>{APP_NAME}</title>
</svelte:head>

<div class="shell" class:wide={media.wide}>
	{#if media.wide}<TopNav />{/if}
	{#if needsData && timetable.status !== 'ready'}
		<DataGate />
	{:else}
		{@render children()}
	{/if}
	{#if !media.wide && showTabs}<BottomNav />{/if}
</div>

<style>
	.shell {
		height: 100dvh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.shell.wide {
		height: auto;
		min-height: 100dvh;
		overflow: visible;
	}
</style>
