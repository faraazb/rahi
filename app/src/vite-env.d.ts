/// <reference types="vite/client" />
interface ImportMetaEnv {
	/** URL of the latest timetable release manifest. */
	readonly VITE_DATA_MANIFEST_URL?: string;
	/** GitHub Pages data folder (pages_data.py layout), e.g. /rahi/data */
	readonly VITE_DATA_ROOT?: string;
}
