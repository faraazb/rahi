"""Helpers shared by the railway adapters: service-day times."""

from __future__ import annotations

from ..model import Diagnostics, Stop

# Trains whose first time is before 03:00 belong to the previous service
# day, so their times are shifted past 24:00 (same boundary Yatri uses).
SERVICE_DAY_START_MIN = 3 * 60


def normalise_times(stops: list[Stop]) -> None:
    """Make times monotonic across midnight and anchor them to the service day."""
    offset = 0
    prev = None
    for s in stops:
        t = s.time_min + offset
        if prev is not None and t < prev - 12 * 60:
            offset += 24 * 60
            t += 24 * 60
        s.time_min = t
        prev = t
    if stops and stops[0].time_min < SERVICE_DAY_START_MIN:
        for s in stops:
            s.time_min += 24 * 60


def fix_twelve_hour_slips(stops: list[Stop], tag: str, diag: Diagnostics) -> None:
    """Correct a time printed 12 hours off ("12:28" between 00:25 and 00:30).

    Only when the time is out of order with both neighbours and moving it by
    exactly 12 hours puts it between them; anything else is left and reported
    as non-monotonic.
    """
    for i in range(1, len(stops) - 1):
        prev, cur, nxt = stops[i - 1].time_min, stops[i].time_min, stops[i + 1].time_min
        if prev <= nxt and not prev <= cur <= nxt:
            for fixed in (cur - 720, cur + 720, cur - 2160, cur + 2160):
                if prev <= fixed <= nxt:
                    diag.add("time-corrected-12h", f"{tag} {stops[i].station_code}",
                             f"printed {cur % 1440 // 60:02d}:{cur % 60:02d}, "
                             f"using {fixed % 1440 // 60:02d}:{fixed % 60:02d}")
                    stops[i].time_min = fixed
                    break
