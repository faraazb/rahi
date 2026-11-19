/** Appearance settings, kept on the device. app.html applies the same keys
 *  before first paint so there is no flash of the wrong theme. */
export type Theme = 'system' | 'light' | 'dark';
export type TextSize = 'small' | 'medium' | 'large';

const KEY = 'rahi.prefs';

interface Stored {
	theme: Theme;
	textSize: TextSize;
	lineColours: boolean;
	h24: boolean;
}

const DEFAULTS: Stored = { theme: 'system', textSize: 'medium', lineColours: true, h24: true };

function read(): Stored {
	try {
		return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') };
	} catch {
		return DEFAULTS;
	}
}

class Prefs {
	theme = $state<Theme>(DEFAULTS.theme);
	textSize = $state<TextSize>(DEFAULTS.textSize);
	lineColours = $state(DEFAULTS.lineColours);
	h24 = $state(DEFAULTS.h24);

	load(): void {
		const s = read();
		this.theme = s.theme;
		this.textSize = s.textSize;
		this.lineColours = s.lineColours;
		this.h24 = s.h24;
	}

	/** Reflect onto <html> and persist. Called from an effect in the layout. */
	apply(): void {
		const r = document.documentElement;
		if (this.theme === 'system') delete r.dataset.theme;
		else r.dataset.theme = this.theme;
		if (this.textSize === 'medium') delete r.dataset.text;
		else r.dataset.text = this.textSize;
		if (this.lineColours) delete r.dataset.lines;
		else r.dataset.lines = 'off';
		const stored: Stored = { theme: this.theme, textSize: this.textSize, lineColours: this.lineColours, h24: this.h24 };
		try {
			localStorage.setItem(KEY, JSON.stringify(stored));
		} catch {
			/* not persisted in private mode */
		}
	}
}

export const prefs = new Prefs();
