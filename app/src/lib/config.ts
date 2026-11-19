export const APP_NAME = 'Rahi';

/** Database schema versions this build of the app can read. */
export const SUPPORTED_SCHEMA = [2, 3];

/** Where to look for the timetable release's manifest, in order: the next URL is
 *  tried only when one answers 404. Assets inside a manifest are resolved
 *  relative to its final URL (after redirects), so the same release folder works
 *  from a GitHub Release layout, GitHub Pages or the local mock server.
 *
 *  On GitHub Pages (VITE_DATA_ROOT, see pipeline/src/mumbailocal/pages_data.py)
 *  the app reads the pointer for the newest schema it supports, so after a schema
 *  change, builds still cached on phones keep getting updates they can read. If
 *  no release of that schema exists yet, latest is a schema the app also reads. */
const dataRoot = import.meta.env.VITE_DATA_ROOT;
export const DATA_MANIFEST_URLS: string[] = import.meta.env.VITE_DATA_MANIFEST_URL
	? [import.meta.env.VITE_DATA_MANIFEST_URL]
	: dataRoot
		? [`${dataRoot}/schema-${Math.max(...SUPPORTED_SCHEMA)}/manifest.json`, `${dataRoot}/latest/manifest.json`]
		: ['/data/faraazb/rahi/releases/latest/download/manifest.json'];
export const DATA_MANIFEST_URL = DATA_MANIFEST_URLS[0];

/** How often to look for a newer timetable while the app is open. */
export const UPDATE_CHECK_EVERY_MS = 6 * 60 * 60 * 1000;

/** Timetable times are Mumbai times whatever the device's time zone. */
export const TIME_ZONE = 'Asia/Kolkata';

/** The operating day runs 03:00 to 03:00; trains after midnight belong to
 *  the previous day's timetable (same convention as the pipeline). */
export const SERVICE_DAY_START_MIN = 180;
