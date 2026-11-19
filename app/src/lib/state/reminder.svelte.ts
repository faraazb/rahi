/** "Remind me before <station>": one reminder at a time, a few minutes
 *  before the scheduled arrival. It fires while the app is open (a PWA
 *  cannot schedule notifications for a closed tab without a push server,
 *  which this app deliberately does not have). */
import { serviceNow } from '#lib/time.ts';

export const LEAD_MIN = 3;

interface Active {
	trainId: number;
	station: string;
	/** Epoch ms when it fires. */
	at: number;
}

class Reminder {
	active = $state<Active | null>(null);
	fired = $state<string | null>(null);
	private timer: ReturnType<typeof setTimeout> | undefined;

	/** Schedule for `arrMinute` (service-day minutes) minus the lead time. */
	async set(trainId: number, station: string, arrMinute: number): Promise<void> {
		const now = serviceNow();
		const at = Date.now() + (arrMinute - LEAD_MIN - now.minute) * 60_000 - (Date.now() % 60_000);
		if ('Notification' in globalThis && Notification.permission === 'default') {
			try {
				await Notification.requestPermission();
			} catch {
				/* in-app banner still works */
			}
		}
		this.clear();
		this.active = { trainId, station, at };
		this.timer = setTimeout(() => this.fire(), Math.max(0, at - Date.now()));
	}

	clear(): void {
		clearTimeout(this.timer);
		this.active = null;
	}

	private async fire(): Promise<void> {
		const a = this.active;
		if (!a) return;
		const text = `${a.station} in about ${LEAD_MIN} minutes. Get ready to get off.`;
		this.fired = text;
		this.active = null;
		navigator.vibrate?.([200, 100, 200]);
		if ('Notification' in globalThis && Notification.permission === 'granted') {
			try {
				const reg = await navigator.serviceWorker?.getRegistration();
				if (reg) await reg.showNotification(`Next: ${a.station}`, { body: text, tag: 'arrival' });
				else new Notification(`Next: ${a.station}`, { body: text });
			} catch {
				/* banner is enough */
			}
		}
	}
}

export const reminder = new Reminder();
