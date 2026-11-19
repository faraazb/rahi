"""Central Railway suburban timetable ("PTT") parser.

Input: the PDFs on (old)cr.indianrailways.gov.in -> Passenger Information ->
Suburban Time Table, one folder per download (`data/raw/cr/<date>/`). Every
file is an Excel sheet printed to PDF (text, no images); `SHEETS` maps file
names to lines:

  main_dn / main_up   CSMT <-> Kalyan -> Karjat/Khopoli and -> Kasara   CR
  main_15car          15-car services on the Main line, both directions CR
  ac                  Main line AC services, both directions            CR
  hb_dn / hb_up       CSMT <-> Goregaon and <-> Panvel                  HR
  hb_ac               Harbour AC services                               HR
  thb                 Thane <-> Vashi / Nerul / Panvel                  THR
  port                Nerul / Belapur <-> Uran                          UR
  lnl_pune / pune_lnl Lonavala <-> Pune                                 PUNE

Sheet conventions this parser relies on (checked on rendered pages):

* Columns are trains. The header holds the 5-digit number and a link code
  ("A 1", "PL 5", "TPL 3": the rake working, not a station). Marks for the
  whole column sit in the header or in unlabelled rows just above the
  first station: "AC", "AC#" / "AC #", "X", "XX", "15 C", "$", "L SPL".
* Rows are stations, but the branches are stacked: the Main sheets list
  CSMT..Kalyan, then the Karjat/Khopoli branch, then the Kasara branch, so
  row order is not travel order. Stops are put in travel order along the
  track graph of `data/stations/<line>.csv` instead.
* A cell holds HH:MM (H:MM in the small hours, HH.MM on the Pune sheets).
  "…" / "..." / "Thr..." mean the train passes without stopping; a blank (or
  "X" on the Pune sheets) means the train does not run there.
* Some cells hold a word instead of a time: "TNA" / "DR" where the train
  comes from a station off the sheet, "R/O", "VVD 2", "PLVD24" (rake
  links). They are kept as notes.
* The Pune sheets have arrival ("A:") and departure ("D:") rows around each
  station row; the last time printed for a station is used.
* Legends: "X" = will not run on Sundays / nominated holidays (printed on the
  HB AC sheet only; the Main and Harbour sheets use the mark without a
  legend). "AC#" = runs non-AC on Saturday, Sunday and holidays. "$" = 3
  coaches at the Thane end reserved for ladies (THB legend). "XX" has no
  legend anywhere and is reported, not interpreted.

Merging. One train can be printed on several sheets of the same line (an AC
train on the Main sheet and the AC sheet, a 15-car train on the Main sheet
and the 15-car sheet). The sheet listed first in `SHEETS` for that line is
the newest edition and wins; the trips of an older sheet with the same number
and direction are dropped, and any difference is reported
(`sheet-superseded`). A train printed on another line's sheet (Trans-Harbour
99003 on the Harbour sheet, "TNA" in its CSMT cell) is dropped in favour of
its own line's sheet (`foreign-copy-dropped`).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from statistics import median

import pdfplumber

from ..model import NOT_SUNDAY, Diagnostics, Stop, Train
from ..pdfgrid import Grid, Word, extract_grids
from ..stations import StationTable, all_codes
from .common import fix_twelve_hour_slips, normalise_times


@dataclass(frozen=True)
class Sheet:
    line: str
    note: str = ""  # what the file is, for diagnostics and docs


# Newest edition first within each line: the order decides merges.
SHEETS: dict[str, Sheet] = {
    "main_15car.pdf": Sheet("CR", "15-car services, w.e.f. 15.08.2026"),
    "ac.pdf": Sheet("CR", "AC services, w.e.f. 16.04.2025"),
    "main_dn.pdf": Sheet("CR", "Main line DN, 2024 edition"),
    "main_up.pdf": Sheet("CR", "Main line UP, 2024 edition"),
    "hb_ac.pdf": Sheet("HR", "Harbour AC, w.e.f. 01.05.2026"),
    "hb_dn.pdf": Sheet("HR", "Harbour DN, w.e.f. 01.05.2026"),
    "hb_up.pdf": Sheet("HR", "Harbour UP, w.e.f. 01.05.2026"),
    "thb.pdf": Sheet("THR", "Trans-Harbour, w.e.f. 13.01.2024"),
    "port.pdf": Sheet("UR", "Port line, w.e.f. 15.12.2025"),
    "lnl_pune.pdf": Sheet("PUNE", "Lonavala -> Pune"),
    "pune_lnl.pdf": Sheet("PUNE", "Pune -> Lonavala"),
}
LINES = ("CR", "HR", "THR", "UR", "PUNE")

# The line a train number belongs to; decides which copy of a train printed
# on two lines' sheets is kept. 9139x / 9149x are Harbour trains numbered in
# the WR series (CSMT <-> Goregaon / Borivali).
HOME_LINE = (("98", "HR"), ("9139", "HR"), ("9149", "HR"),
             ("990", "THR"), ("992", "THR"), ("994", "THR"), ("995", "THR"),
             ("996", "UR"), ("997", "UR"), ("998", "PUNE"), ("999", "PUNE"),
             ("95", "CR"), ("96", "CR"), ("97", "CR"))
# A train printed as two halves in the DN and UP tables, meeting at one
# station (Panvel <-> Goregaon via Vadala: 98901 UP ends at Vadala 06:58,
# 98901 DN leaves Vadala 07:02), is one trip when the halves meet within this.
JOIN_WITHIN_MIN = 30

ANCHOR = re.compile(r"9\d{4}")
HEADER_LABEL_WORDS = frozenset({
    "STATION", "STATIONS", "TRAIN", "NO.", "NO", "CODE", "TR.NO", "TR.CODE", "CODE",
})
TIME = re.compile(r"(\d{1,2})[:.;](\d{2})")
PASS = re.compile(r"(THR)?(\.\.\.|…)+|`")
ABSENT = {"X"}  # Pune sheets: the train does not run at this station
LINK = re.compile(r"([A-Z]{1,5}) ?(\d{1,3})")
CARS = re.compile(r"(\d{2}) ?C(AR)?S?")
ARR_DEP = re.compile(r"\s*\b[AD]:\s*$")
# Header / mark tokens and what they set.
DAY_MARKS = {"X", "XX"}
IGNORED_TOKENS = {"0", "PTT", "C"}  # white zeros in blank rows; Pune "PTT" label


def home_line(number: str) -> str | None:
    return next((line for prefix, line in HOME_LINE if number.startswith(prefix)), None)


def _to_min(m: re.Match[str]) -> int:
    return int(m[1]) * 60 + int(m[2])


@dataclass
class _Cell:
    minutes: int | None = None
    passed: bool = False
    absent: bool = False
    notes: list[str] | None = None


def _parse_cell(words: list[Word]) -> _Cell:
    texts = [w.text for w in words]
    times = [m for t in texts if (m := TIME.fullmatch(t))]
    if times:
        rest = [t for t in texts if not TIME.fullmatch(t) and not PASS.fullmatch(t.upper())]
        return _Cell(minutes=_to_min(times[-1]), notes=rest or None)
    up = [t.upper() for t in texts]
    if up and all(PASS.fullmatch(t) for t in up):
        return _Cell(passed=True)
    if up and all(t in ABSENT for t in up):
        return _Cell(absent=True)
    return _Cell(notes=texts)


def _station_rows(grid: Grid, stations: StationTable, where: str, diag: Diagnostics):
    """[(row index, station)] with the Pune A:/D: rows folded into their station."""
    out: list[tuple[int, object]] = []
    pending_arrival: list[int] = []
    for i, row in enumerate(grid.rows):
        label = row.label.strip()
        if not label:
            continue
        if label in {"A:", "D:"}:
            if label == "A:":
                pending_arrival.append(i)
            elif out:
                out.append((i, out[-1][1]))
            continue
        name = ARR_DEP.sub("", label)
        st, how = stations.match(name)
        if st is None:
            continue
        if how != "exact":
            diag.add(f"station-{how}-match", where, f"{label!r} -> {st.code}")
        out += [(j, st) for j in pending_arrival]
        pending_arrival = []
        out.append((i, st))
    if not out:
        return out
    # Pune sheets print a lone time halfway between the A: and D: lines,
    # on a line of its own: it belongs to the nearest station label.
    named = [(grid.rows[i].top, st) for i, st in out if ARR_DEP.sub("", grid.rows[i].label.strip())]
    tops = [top for top, _ in named]
    pitch = median(b - a for a, b in zip(tops, tops[1:])) if len(tops) > 1 else 15.0
    has_arr_dep = any(grid.rows[i].label.strip() in {"A:", "D:"} for i, _ in out)
    lo, hi = out[0][0], max(i for i, _ in out)
    for i in range(lo, hi + 1):
        row = grid.rows[i]
        if row.label.strip() or not row.cells:
            continue
        top, st = min(named, key=lambda n: abs(n[0] - row.top))
        if abs(top - row.top) <= 0.4 * pitch:
            out.append((i, st))
            if not has_arr_dep:
                diag.add("station-inferred", where, f"unlabelled row -> {st.code}")
    out.sort(key=lambda x: x[0])
    return out


def _header_tokens(texts: list[str]) -> list[str]:
    """Split header lines into marks: "AC #" -> "AC#", "15 C" stays one."""
    out: list[str] = []
    for raw in texts:
        t = re.sub(r"\s+", " ", raw.upper()).strip()
        t = re.sub(r"\bAC ?#", "AC#", t)
        if not t:
            continue
        if ANCHOR.fullmatch(t) or LINK.fullmatch(t) or CARS.fullmatch(t) or t in {"L SPL", "L/SPL"}:
            out.append(t)
        else:
            out += t.split()
    return out


def _grid_trains(grid: Grid, fname: str, sheet: Sheet, stations: StationTable,
                 diag: Diagnostics) -> list[Train]:
    where_page = f"{fname}#{grid.page_number}"
    rows = _station_rows(grid, stations, where_page, diag)
    if not rows:
        diag.add("table-without-stations", where_page, grid.header_label[:60])
        return []
    first_row, last_row = rows[0][0], rows[-1][0]
    # Labelled rows that are neither stations nor A:/D: but carry times.
    known = {i for i, _ in rows}
    for i, row in enumerate(grid.rows[first_row:last_row + 1], first_row):
        if i not in known and row.label.strip() and any(TIME.fullmatch(w.text) for ws in row.cells.values() for w in ws):
            diag.add("station-unknown", where_page, row.label)
    for i, row in enumerate(grid.rows[first_row:last_row + 1], first_row):
        if i not in known and not row.label.strip() and any(TIME.fullmatch(w.text) for ws in row.cells.values() for w in ws):
            diag.add("time-without-station", where_page, " ".join(w.text for ws in row.cells.values() for w in ws))

    hops = [stations.hops_from_root(st.code) for _, st in rows]
    direction = "DN" if hops[-1] > hops[0] else "UP" if hops[-1] < hops[0] else None
    if direction is None:
        diag.add("direction-unknown", where_page, grid.header_label[:60])
        return []

    # Unlabelled rows above the first station belong to the header.
    pre_rows = [r for r in grid.rows[:first_row] if not r.label.strip() or r.label.strip() in {"0"}]
    footer = " ".join(
        " ".join([r.label] + [w.text for ws in sorted(r.cells.values(), key=lambda ws: ws[0].x0) for w in ws])
        for r in grid.rows[last_row + 1:])
    sheet_notes: list[str] = []
    if re.search(r"SUNDAY.{0,30}NON\s*AC\s*RAKE", footer.upper()):
        sheet_notes.append("non-AC rake on Sundays and holidays (sheet footnote)")

    trains: list[Train] = []
    for col in grid.columns:
        where = f"{where_page} col{col.index + 1}"
        texts = col.header_texts() + [" ".join(w.text for w in r.cells.get(col.index, [])) for r in pre_rows]
        tokens = _header_tokens(texts)
        numbers = [t for t in tokens if ANCHOR.fullmatch(t)]
        if not numbers:
            diag.add("column-without-number", where, " / ".join(texts))
            continue
        t = Train(number=numbers[0], line=sheet.line, direction=direction, sources=[where_page])
        for tok in tokens[1:] if tokens[0] == numbers[0] else tokens:
            if tok == t.number:
                continue
            if m := CARS.fullmatch(tok):
                t.cars = int(m[1])
            elif tok == "AC":
                t.is_ac = True
            elif tok == "AC#":
                t.is_ac = True
                t.ac_weekdays_only = True
                t.notes.append("AC#: non-AC on Saturday, Sunday and holidays")
            elif tok == "#":
                # Only "AC#" has a legend; a bare "#" (98193 on the HB sheet,
                # next to L/SPL) is not explained anywhere.
                t.unrecognized_notes.append("# (no legend on the sheet)")
                t.notes.append("mark #")
            elif tok == "X":
                t.service.days = NOT_SUNDAY
                t.service.not_on_holidays = True
            elif tok == "XX":
                t.unrecognized_notes.append("XX (no legend on the sheet)")
                t.notes.append("mark XX")
            elif tok == "$":
                t.notes.append("$: Thane-end 3 coaches reserved for ladies")
            elif tok in {"L SPL", "L/SPL"}:
                t.ladies_special = True
            elif LINK.fullmatch(tok):
                t.notes.append(f"link {tok}")
            elif tok in {"L", "SPL"}:  # "L SPL" split over two lines
                t.ladies_special = True
            elif tok in IGNORED_TOKENS:
                pass
            else:
                diag.add("header-token-unknown", where, tok)
        if t.number in {x.number for x in trains}:
            diag.add("number-repeated-on-page", where, t.number)
        t.notes += sheet_notes

        stops: list[Stop] = []
        seen_pass: list[str] = []
        # A station code from another line printed in a cell ("TNA", "BVI")
        # names the train's off-sheet terminal; the next time in the column is
        # that terminal's, not the row's ("BVI" in the Kurla row, "21:50" in
        # the Tilaknagar row: 91491 reaches Borivali at 21:50).
        external: str | None = None
        # "R/O" ("rake of") names the working that brings the rake in, and the
        # time under it is that working's ("R/O / VVD 2 / 04:56" above 98009's
        # first departure, Vadala 05:06): a note, not a stop.
        rake_note: list[str] | None = None
        for ri, st in rows:
            words = grid.rows[ri].cells.get(col.index, [])
            if not words:
                continue
            cell = _parse_cell(words)
            if not stops and cell.notes and any(n.upper() == "R/O" for n in cell.notes):
                rake_note = []
            if rake_note is not None:
                rake_note += [w.text for w in words if w.text.upper() != "R/O"]
                if cell.minutes is not None:
                    t.notes.append(f"rake of {' '.join(rake_note)}")
                    diag.add("rake-note", f"{where} {t.number}", " ".join(rake_note))
                    rake_note = None
                continue
            off_line = [n for n in cell.notes or [] if n.upper() in _other_codes(sheet.line)]
            if off_line:
                external = off_line[0].upper()
            if cell.minutes is not None and external:
                kind = "destination" if stops else "origin"
                t.external_stops.append(Stop(external, f"{external} (printed in the {st.code} row)",
                                             cell.minutes, [kind]))
                external = None
            elif cell.minutes is not None:
                if stops and stops[-1].station_code == st.code:
                    stops[-1] = Stop(st.code, grid.rows[ri].label, cell.minutes)  # departure after arrival
                else:
                    stops.append(Stop(st.code, grid.rows[ri].label, cell.minutes))
            elif cell.passed:
                if st.code not in seen_pass:
                    seen_pass.append(st.code)
            if cell.notes:
                t.notes.append(f"cell {st.code}: {' '.join(cell.notes)}")
        t.stops = stops
        t.pass_marks = [f"pass@{c}" for c in seen_pass if c not in {s.station_code for s in stops}]
        trains.append(t)
    for w in grid.unassigned:
        diag.add("word-outside-columns", where_page, w.text)
    return trains


def parse_pdf(path: Path, sheet: Sheet, stations: StationTable, diag: Diagnostics) -> list[Train]:
    out: list[Train] = []
    seen: Counter[tuple[str, str]] = Counter()
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            grids = extract_grids(page, pno, ANCHOR, HEADER_LABEL_WORDS, min_anchors=1, drop_white=True)
            if not grids:
                diag.add("page-without-grid", f"{path.name}#{pno}")
            for grid in grids:
                for t in _grid_trains(grid, path.name, sheet, stations, diag):
                    seen[(t.number, t.direction)] += 1
                    if seen[(t.number, t.direction)] > 1:
                        diag.add("number-reused-in-file", f"{t.number} {t.direction}",
                                 f"occurrence {seen[(t.number, t.direction)]} at {t.sources[0]}")
                    out.append(t)
    return out


# ------------------------------------------------------------------ ordering


@cache
def _table(line: str) -> StationTable:
    return StationTable(line)


@cache
def _other_codes(line: str) -> frozenset[str]:
    return frozenset(all_codes()) - set(_table(line).by_code)


def _travel_order(t: Train, stations: StationTable, tag: str, diag: Diagnostics) -> list[str] | None:
    """Stops in travel order along the track; returns the route (all stations)."""
    codes = [s.station_code for s in t.stops]
    if len(codes) < 2:
        return codes

    def farthest(a: str) -> str:
        return max(codes, key=lambda c: len(stations.path(a, c) or []))

    a = farthest(codes[0])
    b = farthest(a)
    route = stations.path(a, b) or []
    pos = {c: i for i, c in enumerate(route)}
    off = [c for c in codes if c not in pos]
    if off:
        diag.add("stop-off-route", tag, f"{off} not between {a} and {b}")
        return None
    t.stops.sort(key=lambda s: pos[s.station_code])
    # Orient by the clock: forwards, the minutes between stops add up to the
    # running time; backwards, to nearly a day per stop.
    times = [s.time_min for s in t.stops]
    fwd = sum((y - x) % 1440 for x, y in zip(times, times[1:]))
    bwd = sum((x - y) % 1440 for x, y in zip(times, times[1:]))
    if bwd < fwd:
        t.stops.reverse()
        route.reverse()
    return route


def _finalise(t: Train, diag: Diagnostics) -> None:
    stations = _table(t.line)
    tag = f"{t.number}{'/' + str(t.variant) if t.variant else ''} {t.direction} {t.line}"
    route = _travel_order(t, stations, tag, diag)
    if route is None:
        t.stops.sort(key=lambda s: s.time_min)
    ext_origin = [s for s in t.external_stops if "origin" in s.markers][:1]
    ext_dest = [s for s in t.external_stops if "destination" in s.markers][:1]
    if len(t.external_stops) > len(ext_origin) + len(ext_dest):
        diag.add("external-terminal-repeated", tag, str([s.station_label for s in t.external_stops]))
    t.external_stops = ext_origin + ext_dest
    whole = ext_origin + t.stops + ext_dest
    normalise_times(whole)
    fix_twelve_hour_slips(whole, tag, diag)
    times = [s.time_min for s in whole]
    if any(b < a for a, b in zip(times, times[1:])):
        diag.add("times-not-monotonic", tag, " ".join(f"{s.station_code}={s.time_min}" for s in whole))
    if len(t.stops) < 2:
        diag.add("train-too-few-stops", tag, str(len(t.stops)))
    if not t.stops:
        return
    t.origin, t.destination = whole[0].station_code, whole[-1].station_code
    if route:
        t.is_fast = len(set(route) - {s.station_code for s in t.stops}) > 0


def _check_direction(t: Train, diag: Diagnostics) -> None:
    if not t.stops:
        return
    stations = _table(t.line)
    tag = f"{t.number}{'/' + str(t.variant) if t.variant else ''} {t.direction} {t.line}"
    # CR numbers DN trains odd and UP trains even.
    want = "DN" if int(t.number[-1]) % 2 else "UP"
    if want != t.direction:
        diag.add("direction-parity-mismatch", tag, f"number says {want}")
    # Direction is the table's; on a line with branches it should agree with
    # the trip itself moving away from (DN) or towards (UP) the root.
    # (Not for a trip that crosses the root side of a junction, such as
    # Panvel -> Vadala -> Goregaon, which moves towards and then away.)
    hops = [stations.hops_from_root(s.station_code) for s in t.stops]
    monotonic = hops == sorted(hops) or hops == sorted(hops, reverse=True)
    h0, h1 = hops[0], hops[-1]
    if monotonic and h0 != h1 and ("DN" if h1 > h0 else "UP") != t.direction:
        diag.add("direction-trip-mismatch", tag, f"{t.origin} -> {t.destination} in a {t.direction} table")


# ------------------------------------------------------------------ merging


def _agreement(a: Train, b: Train) -> tuple[int, int]:
    times = {s.station_code: s.time_min % 1440 for s in a.stops}
    same = sum(1 for s in b.stops if times.get(s.station_code) == s.time_min % 1440)
    common = sum(1 for s in b.stops if s.station_code in times)
    return same, common - same


def _differences(keep: Train, drop: Train) -> str:
    a = {s.station_code: s.time_min % 1440 for s in keep.stops}
    b = {s.station_code: s.time_min % 1440 for s in drop.stops}
    hm = lambda m: f"{m // 60:02d}:{m % 60:02d}"  # noqa: E731
    parts = [f"{c} {hm(a[c])} vs {hm(b[c])}" for c in a if c in b and a[c] != b[c]]
    if only := [c for c in a if c not in b]:
        parts.append(f"only kept {only}")
    if only := [c for c in b if c not in a]:
        parts.append(f"only dropped {only}")
    flags = [f for f, x, y in (("ac", keep.is_ac, drop.is_ac), ("days", keep.service, drop.service),
                                ("cars", keep.cars, drop.cars)) if x != y and y is not None]
    if flags:
        parts.append("flags differ: " + ", ".join(flags))
    return "; ".join(parts)


def _merge(trains: list[Train], diag: Diagnostics) -> list[Train]:
    """Per line, the newest sheet's trips win over older sheets' trips of the same train."""
    rank = {name: i for i, name in enumerate(SHEETS)}
    file_of = lambda t: t.sources[0].split("#")[0]  # noqa: E731
    by_key: dict[tuple[str, str, str], list[Train]] = defaultdict(list)
    for t in trains:
        by_key[(t.line, t.number, t.direction)].append(t)
    out: list[Train] = []
    for (_line, number, direction), trips in by_key.items():
        best_file = min((file_of(t) for t in trips), key=rank.__getitem__)
        keep = [t for t in trips if file_of(t) == best_file]
        for t in trips:
            if file_of(t) == best_file:
                continue
            match = max(keep, key=lambda k: _agreement(k, t))
            diff = _differences(match, t)
            kind = "sheet-duplicate" if not diff else "sheet-superseded"
            diag.add(kind, f"{number} {direction}", f"kept {match.sources[0]}, dropped {t.sources[0]}"
                     + (f": {diff}" if diff else ""))
            # Flags printed only on the older sheet still describe the train.
            match.is_ac = match.is_ac or t.is_ac
            match.ac_weekdays_only = match.ac_weekdays_only or t.ac_weekdays_only
            match.ladies_special = match.ladies_special or t.ladies_special
            match.cars = match.cars or t.cars
            match.sources += t.sources
        out += keep
    return out


def _drop_foreign_copies(trains: list[Train], diag: Diagnostics) -> list[Train]:
    """A train printed on another line's sheet yields to its own line's copy."""
    home = {(t.number, t.direction) for t in trains if t.line == home_line(t.number)}
    out = []
    for t in trains:
        if home_line(t.number) is None:
            diag.add("number-series-unknown", f"{t.number} {t.direction}", f"on the {t.line} sheet; not in HOME_LINE")
        elif t.line != home_line(t.number):
            if (t.number, t.direction) in home:
                diag.add("foreign-copy-dropped", f"{t.number} {t.direction}",
                         f"{t.line} sheet {t.sources[0]}; kept the {home_line(t.number)} sheet")
                continue
            diag.add("foreign-copy-kept", f"{t.number} {t.direction}", f"only on the {t.line} sheet")
        out.append(t)
    return out


def _join_halves(trains: list[Train], diag: Diagnostics) -> list[Train]:
    """Join a DN half and an UP half of one train that meet at one station."""
    by_num: dict[tuple[str, str], list[Train]] = defaultdict(list)
    for t in trains:
        if t.stops:
            by_num[(t.line, t.number)].append(t)
    gone: set[int] = set()
    for (_line, number), trips in by_num.items():
        for a in trips:
            for b in trips:
                if a is b or a.direction == b.direction or id(a) in gone or id(b) in gone:
                    continue
                end, start = a.stops[-1], b.stops[0]
                if end.station_code != start.station_code:
                    continue
                if (start.time_min - end.time_min) % 1440 > JOIN_WITHIN_MIN:
                    continue
                diag.add("joined-across-tables", f"{number} {a.line}",
                         f"{a.direction} {a.origin}->{a.destination} + {b.direction} {b.origin}->{b.destination} "
                         f"at {end.station_code}")
                # Back to clock times; _finalise re-anchors the joined trip.
                a.stops = [Stop(s.station_code, s.station_label, s.time_min % 1440)
                           for s in a.stops[:-1] + b.stops]
                a.direction = "DN" if int(number[-1]) % 2 else "UP"
                a.sources += b.sources
                a.notes += [n for n in b.notes if n not in a.notes]
                a.pass_marks += b.pass_marks
                a.is_ac, a.cars = a.is_ac or b.is_ac, a.cars or b.cars
                gone.add(id(b))
                _finalise(a, diag)
    return [t for t in trains if id(t) not in gone]


# ------------------------------------------------------------------ entry points


def parse_dir(pdf_dir: Path, diag: Diagnostics, exclude: frozenset[str] = frozenset()) -> dict[str, list[Train]]:
    """Parse every known sheet in a CR download folder; trains by line code."""
    names = {p.name for p in pdf_dir.glob("*.pdf")}
    for unknown in sorted(names - set(SHEETS) - {"holidays.pdf"} - exclude):
        diag.add("file-unknown", unknown, "not in cr.SHEETS; skipped")
    paths = [pdf_dir / n for n in SHEETS if n in names and n not in exclude]
    return parse_files(paths, diag)


def parse_files(paths: list[Path], diag: Diagnostics) -> dict[str, list[Train]]:
    raw: list[Train] = []
    for path in paths:
        sheet = SHEETS[path.name]
        raw += parse_pdf(path, sheet, _table(sheet.line), diag)
    trains = _drop_foreign_copies(_merge(raw, diag), diag)
    for t in trains:
        _finalise(t, diag)
    trains = _join_halves(trains, diag)
    for t in trains:
        _check_direction(t, diag)
    by_line: dict[str, list[Train]] = {line: [] for line in LINES}
    for t in trains:
        by_line[t.line].append(t)
    for line, ts in by_line.items():
        ts.sort(key=lambda t: (t.direction, t.stops[0].time_min if t.stops else 0, t.number))
        seen: dict[tuple[str, str], int] = {}
        for t in ts:
            key = (t.number, t.direction)
            t.variant = seen.get(key, 0)
            seen[key] = t.variant + 1
        for (number, direction), n in seen.items():
            if n > 1:
                diag.add("number-shared-by-trips", f"{number} {direction} {line}", f"{n} trips")
    return {line: ts for line, ts in by_line.items() if ts}
