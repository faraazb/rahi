# Rahi app

SvelteKit 3 + Vite 8 PWA (TypeScript, Svelte 5 runes), built as a static single-page app for GitHub
Pages. Run it from the repo root with `mise run data-server` and `mise run dev`; see ../README.md.

```
src/lib/data/      timetable: download, verify, store (Cache Storage), sql.js queries
src/lib/state/     on-device state: preferences, saved routes/stations, clock, reminder
src/lib/home/      Home screen parts (journey bar, suggestions, route cards, next trains)
src/lib/ui/        shared pieces (nav bars, badges, data gate)
src/routes/        screens: /, /trains, /train/[id], /station/[code], /settings/*
src/service-worker offline app shell
```

Config: `VITE_DATA_MANIFEST_URL` (see `.env.development`). For a project site on GitHub Pages,
build with `BASE_PATH=/rahi`.

Only official, scheduled data is shown. The design's platform numbers, live status, coach guide,
station facilities, fares and alerts are left out until a real source exists.
