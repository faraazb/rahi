"""Adapter for NTES schedule pages saved by `mumbailocal.ntes.fetch`.

Two lines no suburban PDF covers:

  DVP  Vasai - Diva - Panvel MEMUs, with the Boisar / Dahanu Road and Pen / Roha
       runs (610xx, 6916x). Panvel <-> Vasai trains leave the Diva line at
       Dativali and join the Vasai line at Kopar's upper level, missing Diva.
  NM   Neral - Matheran hill railway and the Aman Lodge - Matheran shuttles (521xx).

NTES gives arrival and departure at each halt. time_min is the departure
(arrival at the destination) and arr_min the arrival where it differs, so a
15-minute halt at Vasai Road is not hidden. Day numbers carry trains past
midnight. NTES says nothing about holidays, AC or car counts, so those stay
at their defaults (not set) rather than being guessed.

Direction follows the number, as on the Indian Railways network: odd numbers
are DN (away from Mumbai / up the hill), even numbers UP.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import ntes
from ..model import Diagnostics, Service, Stop, Train
from ..stations import StationTable
from .common import SERVICE_DAY_START_MIN

LINES = tuple(ntes.LINE_SERIES)
DAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def _minutes(hhmm: str | None, day: int | None) -> int | None:
    if not hhmm:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", hhmm.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2)) + ((day or 1) - 1) * 1440


def days_of_run(text: str | None) -> str | None:
    """"Daily" -> 1111111, "Mon,Tue,Wed,Thu,Fri" -> 1111100; None if unreadable."""
    t = (text or "").strip().upper()
    if t == "DAILY":
        return "1111111"
    names = [x.strip()[:3] for x in t.split(",") if x.strip()]
    if not names or any(n not in DAY_NAMES for n in names):
        return None
    return "".join("1" if d in names else "0" for d in DAY_NAMES)


def line_of(number: str) -> str | None:
    return next((line for line, p in ntes.LINE_SERIES.items() if p.match(number)), None)


def parse_page(page: str, number: str, line: str, table: StationTable, source: str,
               diag: Diagnostics) -> Train | None:
    d = ntes.parse_page(page, number)
    tag = f"{number} {line}"
    if not d["stops"]:
        diag.add("page-without-grid", source, "no schedule rows")
        return None
    t = Train(number=number, line=line, direction="DN" if int(number) % 2 else "UP",
              sources=[source])
    days = days_of_run(d["days_of_run"])
    if days is None:
        diag.add("header-token-unknown", tag, f"days of run {d['days_of_run']!r}")
    else:
        t.service = Service(days=days)
    if d["name"]:
        t.notes.append(d["name"].removeprefix(number).strip())
    for i, s in enumerate(d["stops"]):
        st = table.lookup(s["code"] or "") or table.lookup(s["station"])
        if st is None:
            diag.add("station-unknown", tag, f"{s['station']} ({s['code']})")
            continue
        arr, dep = _minutes(s["arr"], s["day"]), _minutes(s["dep"], s["day"])
        if arr is None and dep is None:
            diag.add("time-without-station", tag, f"{s['code']}: no time")
            continue
        last = i == len(d["stops"]) - 1
        time_min = arr if last or dep is None else dep
        stop = Stop(st.code, s["station"], time_min)
        if arr is not None and arr != time_min:
            stop.arr_min = arr
        t.stops.append(stop)
    if len(t.stops) < 2:
        diag.add("train-too-few-stops", tag, f"{len(t.stops)} stops")
        return None
    if t.stops[0].time_min < SERVICE_DAY_START_MIN:
        for s in t.stops:
            s.time_min += 1440
            s.arr_min = None if s.arr_min is None else s.arr_min + 1440
    times = [x for s in t.stops for x in (s.arr_min, s.time_min) if x is not None]
    if times != sorted(times):
        diag.add("times-not-monotonic", tag, " ".join(f"{s.station_code}:{s.time_min}" for s in t.stops))
    t.origin, t.destination = t.stops[0].station_code, t.stops[-1].station_code
    route = table.path(t.origin, t.destination) or []
    called = {s.station_code for s in t.stops}
    off_route = called - set(route)
    if off_route:
        diag.add("stop-off-route", tag, f"{sorted(off_route)} not between {t.origin} and {t.destination}")
    t.is_fast = any(c not in called for c in route)
    if t.is_fast:
        diag.add("ntes-passes-station", tag, "does not halt at " + ", ".join(c for c in route if c not in called))
    return t


def parse_dir(raw_dir: Path, diag: Diagnostics) -> dict[str, list[Train]]:
    """Every saved schedule page in raw_dir, by line."""
    out: dict[str, list[Train]] = {line: [] for line in LINES}
    tables = {line: StationTable(line) for line in LINES}
    for path in sorted(raw_dir.glob("*.html")):
        number = path.stem
        line = line_of(number)
        if line is None:
            diag.add("file-unknown", path.name, "number in no NTES line series")
            continue
        t = parse_page(path.read_text(), number, line, tables[line], path.name, diag)
        if t is not None:
            out[line].append(t)
    for line, trains in out.items():
        trains.sort(key=lambda t: (t.stops[0].time_min, t.number))
    return out


def sources(raw_dir: Path) -> dict[str, str]:
    import hashlib
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(raw_dir.glob("*.html"))}
