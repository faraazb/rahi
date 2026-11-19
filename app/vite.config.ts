import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// GitHub Pages serves a project site from /<repo>; set BASE_PATH=/rahi there.
const base = (process.env.BASE_PATH ?? '') as '' | `/${string}`;

const dataProxy = {
	target: process.env.DATA_SERVER ?? 'http://127.0.0.1:8787',
	rewrite: (path: string) => path.replace(/^\/data/, '')
};

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// Every route renders in the browser from the offline timetable.
			// Static routes are prerendered as empty shells; GitHub Pages serves
			// 404.html for the rest (/train/<id>, /station/<code>), which boots
			// the router.
			adapter: adapter({ fallback: '404.html' }),
			paths: { base }
		})
	],
	// /data/* goes to the mock release server (pipeline/tools/data_server.py),
	// so the app and its timetable share one origin: no CORS, no mixed
	// content, and a phone on the LAN needs only the app's address.
	server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy: { '/data': dataProxy } },
	preview: { host: '127.0.0.1', port: 4173, strictPort: true, proxy: { '/data': dataProxy } }
});
