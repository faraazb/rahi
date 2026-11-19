<script lang="ts">
	import House from '@lucide/svelte/icons/house';
	import TrainFront from '@lucide/svelte/icons/train-front';
	import Settings from '@lucide/svelte/icons/settings';
	import { page } from '$app/state';
	import { APP_NAME } from '#lib/config.ts';
	import { href } from '#lib/nav.ts';
	import { section } from './section';
	import Logo from './Logo.svelte';

	const items = [
		{ id: 'home', label: 'Home', icon: House, to: href.home() },
		{ id: 'trains', label: 'Trains', icon: TrainFront, to: href.trains() },
		{ id: 'settings', label: 'Settings', icon: Settings, to: href.settings() }
	] as const;
	const current = $derived(section(page.route.id));
</script>

<header>
	<div class="bar">
		<a class="brand" href={href.home()}><Logo size={28} />{APP_NAME}</a>
		<nav aria-label="Primary">
			{#each items as item (item.id)}
				{@const Icon = item.icon}
				<a href={item.to} aria-current={current === item.id ? 'page' : undefined}>
					<Icon size={18} strokeWidth={2} />{item.label}
				</a>
			{/each}
		</nav>
	</div>
</header>

<style>
	header {
		flex: none;
		border-bottom: 1px solid var(--border);
		background: var(--surface);
		position: sticky;
		top: 0;
		z-index: 10;
	}
	.bar {
		max-width: 1200px;
		margin: 0 auto;
		min-height: 64px;
		padding: 10px 24px;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 12px 24px;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		font-size: 1.0625rem;
		font-weight: 800;
		letter-spacing: -0.01em;
	}
	nav {
		display: flex;
		gap: 4px;
	}
	nav a {
		display: flex;
		align-items: center;
		gap: 8px;
		height: 40px;
		padding: 0 14px;
		border-radius: 999px;
		color: var(--text2);
		font-size: 0.875rem;
		font-weight: 700;
	}
	nav a[aria-current='page'] {
		background: var(--primary-soft);
		color: var(--on-primary-soft);
	}
</style>
