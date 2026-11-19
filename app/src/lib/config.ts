export const APP_NAME = 'Rahi';

/** Manifest of the latest timetable release. Assets inside it are resolved
 *  relative to the manifest's final URL (after redirects), so the same
 *  release folder works from a GitHub Release layout, GitHub Pages or the
 *  local mock server. */
export const DATA_MANIFEST_URL: string =
	import.meta.env.VITE_DATA_MANIFEST_URL ?? '/data/faraazb/rahi/releases/latest/download/manifest.json';

/** Database schema versions this build of the app can read. */
export const SUPPORTED_SCHEMA = [2, 3];

/** How often to look for a newer timetable while the app is open. */
export const UPDATE_CHECK_EVERY_MS = 6 * 60 * 60 * 1000;

/** Timetable times are Mumbai times whatever the device's time zone. */
export const TIME_ZONE = 'Asia/Kolkata';

/** The operating day runs 03:00 to 03:00; trains after midnight belong to
 *  the previous day's timetable (same convention as the pipeline). */
export const SERVICE_DAY_START_MIN = 180;
