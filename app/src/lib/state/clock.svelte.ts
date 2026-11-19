/** "Now", ticking on the minute, so countdowns and lists stay current
 *  without each screen running its own timer. */
import { serviceNow, type ServiceNow } from '#lib/time.ts';

class Clock {
	now = $state<ServiceNow>(serviceNow());
	/** Mumbai hour of day (0-23) for usage stats. */
	hour = $derived(Math.floor((this.now.minute % 1440) / 60));
	private timer: ReturnType<typeof setTimeout> | undefined;

	start(): void {
		const tick = () => {
			this.now = serviceNow();
			clearTimeout(this.timer);
			// Wake just after the next minute boundary.
			this.timer = setTimeout(tick, 60_000 - (Date.now() % 60_000) + 250);
		};
		tick();
		document.addEventListener('visibilitychange', () => {
			if (document.visibilityState === 'visible') tick();
		});
	}
}

export const clock = new Clock();

class Media {
	wide = $state(false);
	start(): void {
		const mq = matchMedia('(min-width: 900px)');
		this.wide = mq.matches;
		mq.addEventListener('change', (e) => (this.wide = e.matches));
	}
}

export const media = new Media();
