<script lang="ts">
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import Download from '@lucide/svelte/icons/download';
	import Star from '@lucide/svelte/icons/star';
	import { timetable } from '#lib/data/timetable.svelte.ts';
	import { href } from '#lib/nav.ts';
	import { prefs, type TextSize, type Theme } from '#lib/state/prefs.svelte.ts';
	import { saved } from '#lib/state/saved.svelte.ts';
	import { relativeDate } from '#lib/time.ts';

	// Fixed palettes so each card previews its theme whatever is active now.
	const LIGHT = { bg: '#F3F4F7', surface: '#FFFFFF', border: '#E0E3E9', text: '#0E1116', text3: '#5F6676', primary: '#2B47D9', lC: '#C8402A', lW: '#1D66C9', lH: '#0B7F74' };
	const DARK = { bg: '#0A0C10', surface: '#14171D', border: '#262A33', text: '#F1F3F6', text3: '#8C93A1', primary: '#8EA2FF', lC: '#FF826A', lW: '#5EA1FF', lH: '#3FCBBC' };
	const themes: { id: Theme; label: string; panes: (typeof LIGHT)[] }[] = [
		{ id: 'light', label: 'Light', panes: [LIGHT] },
		{ id: 'dark', label: 'Dark', panes: [DARK] },
		{ id: 'system', label: 'System', panes: [LIGHT, DARK] }
	];
	const sizes: { id: TextSize; name: string; px: string }[] = [
		{ id: 'small', name: 'Small text', px: '13px' },
		{ id: 'medium', name: 'Default text', px: '16px' },
		{ id: 'large', name: 'Large text', px: '20px' }
	];

	const offlineSub = $derived.by(() => {
		const m = timetable.manifest;
		if (!m) {
			if (timetable.status === 'starting') return 'Loading…';
			return timetable.status === 'downloading' ? 'Downloading…' : 'Not downloaded yet';
		}
		return `${m.lines.map((l) => l.name).join(', ')} · updated ${relativeDate(m.published_at)}`;
	});
</script>

{#snippet toggle(label: string, sub: string, on: boolean, flip: () => void)}
	<button type="button" role="switch" aria-checked={on} class="switch-row" onclick={flip}>
		<span class="text"><span class="label">{label}</span><span class="sub">{sub}</span></span>
		<span class="switch" class:on aria-hidden="true"><span class="knob"></span></span>
	</button>
{/snippet}

<div class="page">
	<main class="page-main settings">
		<h1>Settings</h1>

		<section aria-labelledby="theme-h">
			<h2 id="theme-h" class="eyebrow">Theme</h2>
			<div class="themes" role="radiogroup" aria-labelledby="theme-h">
				{#each themes as th (th.id)}
					<button type="button" role="radio" aria-checked={prefs.theme === th.id} class="theme" onclick={() => (prefs.theme = th.id)}>
						<span class="preview" aria-hidden="true">
							{#each th.panes as p, i (i)}
								<span class="pane" style:background={p.bg}>
									<span class="bar" style:background={p.text}></span>
									<span class="box" style:background={p.surface} style:border-color={p.border}>
										<span class="ln" style:background={p.text3}></span>
										<span class="ln short" style:background={p.text3}></span>
										<span class="cta" style:background={p.primary}></span>
									</span>
									<span class="lines"><span style:background={p.lC}></span><span style:background={p.lW}></span><span style:background={p.lH}></span></span>
								</span>
							{/each}
						</span>
						<span class="radio-label"><span class="radio"></span>{th.label}</span>
					</button>
				{/each}
			</div>
		</section>

		<section aria-labelledby="disp-h">
			<h2 id="disp-h" class="eyebrow">Display</h2>
			<div class="card group">
				<div class="size-row">
					<span id="ts-l" class="label">Text size</span>
					<div class="segmented" role="radiogroup" aria-labelledby="ts-l">
						{#each sizes as z (z.id)}
							<button type="button" role="radio" aria-checked={prefs.textSize === z.id} aria-label={z.name} style:font-size={z.px} onclick={() => (prefs.textSize = z.id)}>Aa</button>
						{/each}
					</div>
				</div>
				{@render toggle('Line colours', 'Colour-code lines across the app', prefs.lineColours, () => (prefs.lineColours = !prefs.lineColours))}
				{@render toggle('24-hour time', prefs.h24 ? 'Show 18:42 instead of 6:42 pm' : 'Show 6:42 pm instead of 18:42', prefs.h24, () => (prefs.h24 = !prefs.h24))}
			</div>
		</section>

		<section aria-labelledby="gen-h">
			<h2 id="gen-h" class="eyebrow">General</h2>
			<div class="card group">
				<a class="link-row" href={href.savedStations()}>
					<Star size={22} />
					<span class="text"><span class="label">Saved stations</span></span>
					<span class="value num">{saved.stations.length}</span>
					<ChevronRight size={20} />
				</a>
				<a class="link-row" href={href.offline()}>
					<Download size={22} />
					<span class="text"><span class="label">Offline timetable</span><span class="sub">{offlineSub}</span></span>
					<ChevronRight size={20} />
				</a>
			</div>
		</section>
	</main>
</div>

<style>
	.settings {
		padding-top: calc(env(safe-area-inset-top, 0px) + 44px);
		gap: 20px;
	}
	h1 {
		font-size: 2rem;
		line-height: 1.1;
		font-weight: 800;
		letter-spacing: -0.025em;
	}
	section {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.themes {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 10px;
	}
	.theme {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 8px 8px 12px;
		border-radius: 18px;
		border: 1px solid var(--border);
		background: var(--surface);
	}
	.theme[aria-checked='true'] {
		border: 2px solid var(--primary);
		padding: 7px 7px 11px;
	}
	.preview {
		height: 104px;
		display: flex;
		border-radius: 12px;
		overflow: hidden;
		border: 1px solid var(--border);
	}
	.pane {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 5px;
		padding: 8px 6px;
	}
	.bar {
		height: 6px;
		width: 60%;
		border-radius: 3px;
	}
	.box {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 5px;
		border-radius: 6px;
		border: 1px solid;
	}
	.ln {
		height: 4px;
		width: 70%;
		border-radius: 2px;
	}
	.ln.short {
		width: 50%;
	}
	.cta {
		margin-top: auto;
		height: 10px;
		border-radius: 4px;
	}
	.lines {
		display: flex;
		gap: 3px;
	}
	.lines span {
		height: 5px;
		flex: 1;
		border-radius: 3px;
	}
	.radio-label {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		font-size: 0.875rem;
		font-weight: 700;
	}
	.radio {
		width: 16px;
		height: 16px;
		border-radius: 999px;
		border: 2px solid var(--text3);
	}
	[aria-checked='true'] .radio {
		border: 5px solid var(--primary);
	}
	.group {
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.size-row {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 14px 16px;
	}
	.label {
		font-size: 0.9375rem;
		font-weight: 700;
	}
	.segmented {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 4px;
		padding: 4px;
		border-radius: 12px;
		background: var(--surface2);
	}
	.segmented button {
		height: 40px;
		border: 0;
		border-radius: 9px;
		background: transparent;
		color: var(--text2);
		font-weight: 800;
	}
	.segmented button[aria-checked='true'] {
		background: var(--surface);
		color: var(--text);
		box-shadow: var(--shadow);
	}
	.switch-row,
	.link-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 14px;
		min-height: 64px;
		padding: 10px 16px;
		border: 0;
		border-top: 1px solid var(--border);
		background: transparent;
		text-align: left;
	}
	.link-row {
		min-height: 56px;
		color: var(--text);
	}
	.link-row:first-child {
		border-top: 0;
	}
	.link-row :global(svg:last-child) {
		color: var(--text3);
	}
	.text {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.link-row .label {
		font-weight: 600;
	}
	.sub {
		font-size: 0.8125rem;
		color: var(--text3);
	}
	.value {
		font-size: 0.875rem;
		color: var(--text3);
	}
	.switch {
		flex: none;
		width: 48px;
		height: 28px;
		padding: 3px;
		border-radius: 999px;
		display: flex;
		justify-content: flex-start;
		background: var(--border);
		transition: background 0.15s;
	}
	.switch.on {
		justify-content: flex-end;
		background: var(--primary);
	}
	.knob {
		width: 22px;
		height: 22px;
		border-radius: 999px;
		background: #fff;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
	}
</style>
