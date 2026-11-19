<script lang="ts">
	import House from '@lucide/svelte/icons/house';
	import TrainFront from '@lucide/svelte/icons/train-front';
	import Settings from '@lucide/svelte/icons/settings';
	import { page } from '$app/state';
	import { href } from '#lib/nav.ts';
	import { section } from './section';

	const items = [
		{ id: 'home', label: 'Home', icon: House, to: href.home() },
		{ id: 'trains', label: 'Trains', icon: TrainFront, to: href.trains() },
		{ id: 'settings', label: 'Settings', icon: Settings, to: href.settings() }
	] as const;
	const current = $derived(section(page.route.id));
</script>

<nav aria-label="Primary">
	{#each items as item (item.id)}
		{@const Icon = item.icon}
		<a href={item.to} aria-current={current === item.id ? 'page' : undefined}>
			<span class="pill"><Icon size={22} strokeWidth={1.9} /></span>{item.label}
		</a>
	{/each}
</nav>

<style>
	nav {
		flex: none;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		padding: 6px 8px calc(env(safe-area-inset-bottom, 0px) + 10px);
		background: var(--nav-bg);
		border-top: 1px solid var(--border);
	}
	a {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		min-height: 52px;
		padding-top: 4px;
		color: var(--text3);
		font-size: 0.75rem;
		font-weight: 600;
	}
	.pill {
		width: 56px;
		height: 30px;
		display: grid;
		place-items: center;
		border-radius: 999px;
	}
	a[aria-current='page'] {
		color: var(--text);
		font-weight: 700;
	}
	a[aria-current='page'] .pill {
		background: var(--primary-soft);
		color: var(--on-primary-soft);
	}
</style>
