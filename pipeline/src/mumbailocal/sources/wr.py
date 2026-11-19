"""Western Railway suburban timetable ("PTT") parser.

Input: the PDFs on wr.indianrailways.gov.in -> Mumbai Suburban -> Suburban
Time Table. They are Excel sheets printed to PDF (text, no images):

  main DN / UP sheets   Churchgate <-> Virar, one train per column
  AC DN / UP sheets     same layout, AC services only
  Dahanu Road sheet     Churchgate/Virar <-> Dahanu Road; its header stacks
                        car count, number, origin and destination

Sheet conventions this parser relies on (verified against rendered pages):

* Column header: a station code, a 5-digit train number (sometimes with a
  letter suffix, e.g. 90217A) and a car count. On the main sheets the single
  code is the train's far terminal - the destination of a DN train, the
  origin of an UP train. The Dahanu sheet prints origin and destination.
  Codes may carry footnote marks (BVI*, NSP#).
* Cells hold HH:MM. A blank cell means no stop. "P" marks a station passed
  without halting, "T" a non-passenger halt, "--" a pass.
* The terminal's own cell is sometimes left blank (e.g. 90305 to Borivali has
  no Borivali time). The header still names the terminal; no time is invented.
* Notes ("NOT ON SUN ONLY", "Air Condition", "ON SAT & SUN NON AC", "Ladies
  Special / On Sun General") are printed vertically inside the train's column.
* One number is occasionally printed on two different trips in the same sheet
  (94083 runs 06:35 to Virar and 08:46 to Borivali). Repeats within a file are
  kept as separate trips (variant 1, 2, ...).
* Dahanu trains appear on the main sheet up to Virar and on the Dahanu sheet
  beyond, so trains are merged across files by number and direction.

Additions in PTT-79 (01.09.2026):

* The Dahanu sheet stacks a DN table and an UP table on one page.
* AC sheets are labelled "DN AC TRAINS" / "UP AC TRAINS" under the numbers.
* Central Railway Harbour trains running over WR (CSMT <-> Bandra / Goregaon)
  have their own columns. The header reads "C.R.GMN", "C.R.CSMT", ...: the
  code is the destination in both directions. The CSMT end is a note plus a
  time in an unrelated row ("EX / CSMT / 04:28" in the Prabhadevi row,
  "CSTM / Arr / 06:00" in the Mumbai Central row); that time belongs to CSMT.
* A few such columns carry a token like "WGN 1" or "WBO1" instead of a code
  (a link or rake label); it is kept as a note.

Older releases (2017-2023, pinned in tests/test_wr_releases.py):

* Direction is taken from the order of the station rows; the "DN"/"UP"
  label moves between releases or is missing (booklet page titles only).
* Booklet spreads: two booklet pages per PDF page, sometimes with the
  station column in the middle.
* Station labels with markers or truncation ("CHURCHGATE D", "Grant Road
  C/S", "CHURCHGAT", "Ville Parle") match loosely and are reported.
* Specials are numbered "SPL-1"; empty runs ("ETY") and MEMU/passenger
  trains on old Dahanu sheets are skipped.
* Truncated train numbers: columns come from the car-count row instead.
* Rows with times but no label: inferred only in two narrow shapes.
* Not supported: the 2022 SWTT-76 combined AC sheet.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from statistics import median

import pdfplumber

from ..model import NOT_SUNDAY, SUNDAY_ONLY, Diagnostics, Stop, Train
from ..pdfgrid import Grid, Word, extract_grids, group_lines
from ..stations import StationTable
from .common import fix_twelve_hour_slips as _fix_twelve_hour_slips
from .common import normalise_times as _normalise_times

LINE = "WR"
# Train numbers: 5 digits, sometimes a letter suffix (90217A); specials are
# printed "SPL-1", "SPL-2" (2021-22 sheets).
ANCHOR = re.compile(r"\d{5}[A-Z]?|SPL-?\d{1,2}")
# Mumbai suburban EMUs are numbered 9xxxx. Older Dahanu sheets also list MEMU,
# DMU and passenger trains (59xxx, 61xxx, 69xxx, 71xxx); those are not locals.
SUBURBAN_NUMBER = re.compile(r"9\d{4}[A-Z]?|SPL-?\d{1,2}")
# Header words that describe the run rather than name a station: "ETY" an
# empty (non-passenger) run, "C/S" car shed, "T/LINE" through line.
RUN_LABELS = {"ETY", "C/S", "T/LINE"}
HEADER_LABEL_WORDS = frozenset({"STATIONS", "TRAINS", "DN", "UP", "AC", "ACTRAINS"})
# ";" occurs as a typo for ":" ("20;02").
TIME = re.compile(r"(?P<pre>[^\d]*)(?P<h>\d{1,2})[:.;](?P<m>\d{2})(?::\d{2})?(?P<suf>[^\d]*)")
CODE = re.compile(r"([A-Z]{2,5})([*#]*)")
CODE_PAIR = re.compile(r"([A-Z]{2,5})-([A-Z]{2,5})")
CARS = re.compile(r"(\d{1,2})CARS?")
FOREIGN = re.compile(r"C\.R\.([A-Z]{2,5})")  # Central Railway train, its destination
LINK = re.compile(r"W[A-Z]{2}\d{1,2}")  # "WGN 1", "WBO1"
# Terminals off the WR line that the sheet times in a note, with misspellings.
EXTERNAL = {"CSMT": "CSMT", "CSTM": "CSMT", "PNVL": "PNVL"}
PASS_MARKS = {"--", "-", "—", "–"}
# Single tokens printed in a cell instead of a time.
CELL_MARKERS = {"P": "pass", "T": "tech-halt", "TO": "to", "O/L": "o/l"}
# Allowed disagreement between the main sheet and the Dahanu sheet.
MERGE_TOLERANCE_MIN = 2


def _to_min(m: re.Match[str]) -> int:
    return int(m["h"]) * 60 + int(m["m"])


def _direction(header_label: str) -> str | None:
    u = header_label.upper()
    has_dn = re.search(r"\bDN\b|\bDOWN\b", u) is not None
    has_up = re.search(r"\bUP\b", u) is not None
    if has_dn != has_up:
        return "DN" if has_dn else "UP"
    return None


def _parse_header(texts: list[str], where: str, diag: Diagnostics, stations: StationTable | None = None):
    """Classify a column's header tokens by pattern, not by row position."""
    number = cars = operator = None
    codes: list[str] = []
    marks: list[str] = []
    labels: list[str] = []
    def classify(t: str, raw: str) -> bool:
        nonlocal number, cars, operator
        if m := FOREIGN.fullmatch(t):
            operator = "CR"
            codes.append(m[1])
        elif LINK.fullmatch(t) or t in RUN_LABELS:
            labels.append(raw)
        elif ANCHOR.fullmatch(t):
            number = t
        elif m := CARS.fullmatch(t):
            cars = int(m[1])
        elif m := CODE_PAIR.fullmatch(t):
            codes.extend([m[1], m[2]])
        elif (m := re.fullmatch(r"([A-Z]{2,5}-[A-Z]{2,5})\1", t)) and (m := CODE_PAIR.fullmatch(m[1])):
            # Two neighbouring headers printed touching ("DRD-CCGDRD-CCG").
            diag.add("header-tokens-touching", where, raw)
            codes.extend([m[1], m[2]])
        elif (m := CODE.fullmatch(t)) and (stations is None or m[1] in stations.by_code
                                           or not (len(m[1]) >= 4 and stations.match(m[1])[0])):
            codes.append(m[1])
            if m[2]:
                marks.append(t)
        elif stations and len(t) >= 4 and (st := stations.match(raw)[0]):
            # Older Dahanu sheets name the terminals in full ("VIRAR", "DAHANU").
            codes.append(st.code)
        else:
            return False
        return True

    for raw in texts:
        t = raw.replace(" ", "").upper()
        if not t or classify(t, raw):
            continue
        # A crowded header puts more than one item in a column's line
        # ("1 90361", "12 CAR 12", "VR C/S"): classify word by word, pairing
        # a number with a following CAR.
        words = raw.upper().split()
        i = 0
        while i < len(words):
            w = words[i]
            if i + 1 < len(words) and w.isdigit() and words[i + 1].startswith("CAR"):
                w, i = w + words[i + 1], i + 1
            if not classify(w, w):
                if w.isdigit() and len(w) <= 2:
                    pass  # a stray footnote number or a neighbour's car count
                else:
                    diag.add("header-token-unknown", where, w)
            i += 1
    return number, cars, codes, marks, operator, labels


def _parse_cell(words: list[Word]):
    """Return (minutes | None, markers, note_words, cell_marker, extra_times)."""
    texts = [w.text for w in words]
    # Letter-spaced times ("1 2 : 5 9") arrive as single-character words.
    if len(words) > 1 and all(re.fullmatch(r"[\d:.;]", t) for t in texts):
        if m := TIME.fullmatch("".join(texts)):
            return _to_min(m), [], [], None, 0
    minutes = None
    extra = 0
    markers: list[str] = []
    others: list[Word] = []
    for w in words:
        m = TIME.fullmatch(w.text)
        if m and not m["pre"].isalpha() and not m["suf"].isalpha():
            if minutes is None:
                minutes = _to_min(m)
                markers += [x for x in (m["pre"], m["suf"]) if x]
            else:
                extra += 1
        else:
            others.append(w)
    if minutes is not None:
        # Short tokens on the same line as a time are markers (*, P, T, #).
        return minutes, markers + [w.text for w in others], [], None, extra
    joined = "".join(texts).upper()
    if others and all(w.text in PASS_MARKS for w in others):
        return None, [], [], "pass", 0
    # "P*": a pass whose footnote mark explains it.
    if joined.rstrip("*#") in CELL_MARKERS:
        return None, [], [], CELL_MARKERS[joined.rstrip("*#")], 0
    return None, [], others, None, 0


def _phrases(words: list[Word], row_pitch: float) -> list[str]:
    """Join a column's note words into phrases, top to bottom, left to right."""
    out: list[str] = []
    current: list[str] = []
    last_top = None
    for ln in group_lines(words):
        if last_top is not None and ln.top - last_top > 1.6 * row_pitch:
            out.append(" ".join(current))
            current = []
        current.append(ln.text)
        last_top = ln.top
    if current:
        out.append(" ".join(current))
    return [p for p in out if p.strip() and p.strip() not in PASS_MARKS]


# Words that are understood somewhere in the rules below. A phrase made only
# of these (plus punctuation) is fully recognised.
KNOWN_NOTE_WORDS = {
    "AIR", "CONDITION", "AC", "NON", "ON", "NOT", "SAT", "SATURDAY", "SUN",
    "SUNDAY", "ONSUN", "ONLY", "HOLIDAY", "HOLIDAYS", "LADIES", "LADIE", "SPECIAL",
    "SPL", "GENERAL", "GEN", "NOS", "AND", "PASSING", "WILL", "HALT", "AT", "SA", "SU",
}
# Abbreviations used in some notes ("*NON AC SA & SU").
NOTE_ALIASES = {"SA": "SAT", "SU": "SUN"}


def _apply_notes(train: Train, phrases: list[str], stations: StationTable) -> None:
    """Interpret the whole column's notes as one bag of tokens.

    Notes are often split across lines or interleaved, e.g. "# NON" / "& SUN" /
    "AC ON SAT", so rules test for token co-occurrence, not exact phrases.
    """
    train.notes += phrases
    text = " ".join(phrases).upper()
    tokens = {NOTE_ALIASES.get(t, t) for t in re.findall(r"[A-Z]+", text)}
    has = lambda *ws: all(w in tokens for w in ws)  # noqa: E731
    sun = bool(tokens & {"SUN", "SUNDAY", "ONSUN"})

    if has("AIR", "CONDITION") or text.strip() in {"AC", "A.C."}:
        train.is_ac = True
    if has("NON", "AC") and sun and bool(tokens & {"SAT", "SATURDAY"}):
        train.is_ac = True
        train.ac_weekdays_only = True
    if "NOT" in tokens and sun:
        train.service.days = NOT_SUNDAY
        if tokens & {"HOLIDAY", "HOLIDAYS"}:
            train.service.not_on_holidays = True
    elif "ONLY" in tokens and sun:
        train.service.days = SUNDAY_ONLY
    elif sun and not tokens & {"GENERAL", "GEN", "NON"}:
        # "SUN & HOLIDAY" with no NOT/ONLY: most likely a lost "NOT ON" line,
        # but the sheet doesn't say so. Left as daily; reviewed by hand.
        train.unrecognized_notes.append("ambiguous day note: " + " / ".join(phrases))
    if tokens & {"LADIES", "LADIE"}:
        train.ladies_special = True

    for p in phrases:
        words = set(re.findall(r"[A-Z]+", p.upper()))
        unknown = words - KNOWN_NOTE_WORDS - set(stations.by_code)
        if unknown or not words:
            train.unrecognized_notes.append(p)


def _legend(footer_rows) -> dict[str, str]:
    """Parse footer lines like "# NOT ON SUNDAY *Ladies Special On Sun.General"."""
    legend: dict[str, str] = {}
    for row in footer_rows:
        words = sorted((w for ws in row.cells.values() for w in ws), key=lambda w: w.x0)
        text = " ".join([row.label] + [w.text for w in words]).strip()
        for m in re.finditer(r"([#*])\s*([^#*]+)", text):
            meaning = m[2].strip()
            if meaning and not TIME.fullmatch(meaning):
                legend.setdefault(m[1], meaning)
    return legend


def _external_terminal(words: list[Word]) -> tuple[str, str, str] | None:
    """("CSMT", "origin" | "destination", printed text) for "EX CSMT" / "CSTM Arr"."""
    toks = [w.text.upper().strip(".") for w in words]
    code = next((EXTERNAL[t] for t in toks if t in EXTERNAL), None)
    if code is None:
        return None
    if "EX" in toks:
        kind = "origin"
    elif "ARR" in toks:
        kind = "destination"
    else:
        return None
    return code, kind, " ".join(w.text for w in words)


def _infer_unlabelled_rows(body, stations: StationTable) -> dict:
    """Station for a row of times printed without its label.

    Two shapes, both seen in WR sheets:

    * Tall merged cells (2022 Dahanu sheet): the name sits at the top of the
      cell ("DADAR") and its times on a later line. The first timed row
      with no label belongs to the labelled row above it when that row has
      no times of its own.
    * A missing label (2018 p.12 omits "Ram Mandir"): the single unlabelled
      timed row between two labelled rows exactly one station apart.

    Anything else stays unassigned and reported.
    """
    timed = lambda r: any(TIME.fullmatch(w.text) for ws in r.cells.values() for w in ws)  # noqa: E731
    labelled = [(i, st) for i, r in enumerate(body) if r.label and (st := stations.lookup(r.label))]
    by_seq = {s.seq: s for s in stations.ordered}
    out = {}
    for (i, a), nxt in zip(labelled, labelled[1:] + [(len(body), None)]):
        j = nxt[0]
        gaps = [k for k in range(i + 1, j) if not body[k].label and timed(body[k])]
        if not timed(body[i]) and gaps:
            out[gaps[0]] = a  # a dotted filler line may sit between name and time
        elif len(gaps) == 1 and nxt[1] is not None and abs(a.seq - nxt[1].seq) == 2:
            out[gaps[0]] = by_seq[(a.seq + nxt[1].seq) // 2]
    return out


def _direction_of(grid: Grid, station_idx: list[int], stations: StationTable,
                  where: str, diag: Diagnostics) -> str | None:
    """DN if the station rows run away from Churchgate, UP if towards it.

    The row order is what the table actually shows; the "DN TRAINS" / "UP"
    label moves around between releases (or is missing), so it is only a
    cross-check and a fallback for a table with fewer than two stations.
    """
    seqs = [stations.lookup(grid.rows[i].label).seq for i in station_idx]
    by_rows = None
    if len(seqs) >= 2 and seqs[0] != seqs[-1]:
        by_rows = "DN" if seqs[-1] > seqs[0] else "UP"
    by_label = _direction(grid.header_label)
    if by_rows and by_label and by_rows != by_label:
        diag.add("direction-label-conflict", where, f"rows say {by_rows}, label says {by_label}")
    direction = by_rows or by_label
    if direction is None:
        diag.add("direction-unknown", where, grid.header_label)
    return direction


def _split(grid: Grid, stations: StationTable):
    """The table body ends at the last station row; below it is the footer."""
    station_idx = [i for i, r in enumerate(grid.rows) if r.label and stations.lookup(r.label)]
    last = station_idx[-1] if station_idx else len(grid.rows) - 1
    return station_idx, grid.rows[: last + 1], grid.rows[last + 1 :]


def _grid_trains(grid: Grid, fname: str, stations: StationTable, diag: Diagnostics,
                 file_legend: dict[str, str]) -> list[Train]:
    where_page = f"{fname}#{grid.page_number}"
    station_idx, body, footer = _split(grid, stations)
    if not station_idx:
        # e.g. a row of next-working train numbers under a Dahanu table.
        diag.add("table-without-stations", where_page, grid.header_label[:60])
        return []
    direction = _direction_of(grid, station_idx, stations, where_page, diag)
    if direction is None:
        return []
    legend = _legend(footer)

    tops = [grid.rows[i].top for i in station_idx]
    row_pitch = median(b - a for a, b in zip(tops, tops[1:])) if len(tops) > 1 else 15.0

    trains: dict[int, Train] = {}
    note_words: dict[int, list[Word]] = {}
    # Note words seen in a column since its last time; they may name an
    # off-line terminal whose time comes next ("EX CSMT" then "04:28").
    pending_from: dict[int, int] = {}
    for col in grid.columns:
        where = f"{where_page} col{col.index + 1}"
        number, cars, codes, marks, operator, labels = _parse_header(col.header_texts(), where, diag, stations)
        if number is None:
            diag.add("column-without-number", where, " / ".join(col.header_texts()))
            continue
        if not SUBURBAN_NUMBER.fullmatch(number):
            diag.add("non-suburban-train", where, number)
            continue
        if any(x.upper() == "ETY" for x in labels):
            diag.add("empty-run-skipped", where, number)
            continue
        for code in codes:
            if code not in stations.by_code and code not in EXTERNAL.values():
                diag.add("header-code-unknown", where, code)
        t = Train(number=number, line=LINE, direction=direction, cars=cars, sources=[where_page],
                  operator=operator)
        if operator and codes:  # "C.R.GMN": destination in either direction
            t.destination = codes[-1]
        elif len(codes) >= 2:  # explicit origin and destination (Dahanu sheet)
            t.origin, t.destination = codes[0], codes[-1]
        elif codes:  # far terminal only
            if direction == "DN":
                t.destination = codes[0]
            else:
                t.origin = codes[0]
        t.notes += [f"header mark {m}" for m in marks] + [f"header {x}" for x in labels]
        trains[col.index] = t
        note_words[col.index] = []
        pending_from[col.index] = 0

    inferred = _infer_unlabelled_rows(body, stations)
    previous = None
    for ri, row in enumerate(body):
        station, how = stations.match(row.label) if row.label else (None, "")
        if station is None and ri in inferred:
            station, how = inferred[ri], "exact"  # reported here, not as a loose match
            diag.add("station-inferred", where_page, f"unlabelled row -> {station.code}")
        if station is None and row.label.strip().upper() in {"A", "D"} and previous is not None:
            # "VIRAR A" then a row labelled only "D": arrival and departure of
            # the same station. The departure is kept (it overwrites below).
            station, how = previous, "exact"
        previous = station or previous
        if station and how != "exact":
            diag.add(f"station-{how}-match", where_page, f"{row.label!r} -> {station.code}")
        if row.label and station is None:
            if any(TIME.fullmatch(w.text) for ws in row.cells.values() for w in ws):
                diag.add("station-unknown", where_page, row.label)
            continue
        for ci, words in row.cells.items():
            if ci not in trains:
                continue
            t = trains[ci]
            minutes, markers, notes, cell_marker, extra = _parse_cell(words)
            if extra:
                diag.add("cell-multiple-times", f"{where_page} {t.number}",
                         " ".join(w.text for w in words))
            if minutes is not None:
                ext = _external_terminal(note_words[ci][pending_from[ci]:] + words)
                if ext:
                    code, kind, text = ext
                    t.external_stops.append(Stop(code, text, minutes, [kind]))
                    del note_words[ci][pending_from[ci]:]
                    continue
                pending_from[ci] = len(note_words[ci]) + len(notes)
                if station is None:
                    diag.add("time-without-station", f"{where_page} {t.number}",
                             " ".join(w.text for w in words))
                    continue
                if t.stops and t.stops[-1].station_code == station.code:
                    t.stops[-1] = Stop(station.code, row.label, minutes, markers)
                else:
                    t.stops.append(Stop(station.code, row.label, minutes, markers))
            elif cell_marker and station is not None:
                t.pass_marks.append(f"{cell_marker}@{station.code}")
            note_words[ci] += notes

    label = grid.header_label.upper()
    sheet_is_ac = "AIR CONDITIONED" in label or re.search(r"\bAC\s*TRAINS\b", label) is not None
    for ci, train in trains.items():
        phrases = _phrases(note_words[ci], row_pitch)
        _apply_notes(train, phrases, stations)
        if sheet_is_ac:
            train.is_ac = True
        # Symbol marks take their meaning from this page's legend.
        used = set("".join(m for m in train.notes if m.startswith("header mark ")))
        used |= set("".join(phrases)) | {c for s in train.stops for m in s.markers for c in m}
        for mark in sorted(used & {"#", "*"}):
            meaning = legend.get(mark)
            if meaning is None:
                # Some pages omit the footer; use the meaning the mark has on
                # most pages of the same sheet, and say so.
                meaning = file_legend.get(mark)
                if meaning is None:
                    diag.add("mark-without-legend", f"{where_page} {train.number}", mark)
                    continue
                diag.add("legend-from-other-pages", f"{where_page} {train.number}", f"{mark} {meaning}")
            if re.search(r"PASSING|HALT", meaning.upper()):
                # "* Passing (Will not halt at BVI)": the named station, or the
                # starred times, are passes rather than halts.
                at = re.search(r"AT\s+([A-Z][A-Z .']+)", meaning.upper())
                target = stations.lookup(at[1].strip(" .)")) if at else None
                for st in list(train.stops):
                    if (target and st.station_code == target.code) or any(mark in m for m in st.markers):
                        train.stops.remove(st)
                        train.pass_marks.append(f"pass{mark}@{st.station_code}")
            else:
                _apply_notes(train, [f"{mark} {meaning}"], stations)

    for w in grid.unassigned:
        diag.add("word-outside-columns", where_page, w.text)
    return list(trains.values())


def _meaning_kind(meaning: str) -> str:
    u = meaning.upper()
    if re.search(r"PASSING|HALT", u):
        return "pass"
    if "LADIES" in u:
        return "ladies"
    if re.search(r"NON\s*AC", u):
        return "non-ac-weekend"
    if "NOT" in u:
        return "not-on"
    return u.split()[0] if u.split() else ""


def _file_legend(grids: list[Grid], stations: StationTable) -> dict[str, str]:
    """For each mark, the meaning it has on most pages of this file."""
    by_mark: dict[str, list[str]] = {}
    for grid in grids:
        for mark, meaning in _legend(_split(grid, stations)[2]).items():
            by_mark.setdefault(mark, []).append(meaning)
    out: dict[str, str] = {}
    for mark, meanings in by_mark.items():
        kinds = Counter(_meaning_kind(m) for m in meanings)
        top = kinds.most_common(1)[0][0]
        out[mark] = Counter(m for m in meanings if _meaning_kind(m) == top).most_common(1)[0][0]
    return out


def parse_pdf(path: Path, stations: StationTable, diag: Diagnostics) -> list[Train]:
    grids: list[Grid] = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            # min_anchors=1: the last page of a sheet can hold a single train.
            found = extract_grids(page, pno, ANCHOR, HEADER_LABEL_WORDS, min_anchors=1, column_re=CARS)
            if not found:
                diag.add("page-without-grid", f"{path.name}#{pno}")
            grids += found
    file_legend = _file_legend(grids, stations)

    out: list[Train] = []
    seen: Counter[tuple[str, str]] = Counter()
    for grid in grids:
        for t in _grid_trains(grid, path.name, stations, diag, file_legend):
            seen[(t.number, t.direction)] += 1
            if seen[(t.number, t.direction)] > 1:
                diag.add("number-reused-in-file", f"{t.number} {t.direction}",
                         f"occurrence {seen[(t.number, t.direction)]} at {t.sources[0]}")
            out.append(t)
    return out


def _agreement(a: Train, b: Train) -> tuple[int, int]:
    """(stations with matching times, stations with conflicting times)."""
    times = {s.station_code: s.time_min for s in a.stops}
    match = conflict = 0
    for s in b.stops:
        if s.station_code in times:
            if abs(times[s.station_code] - s.time_min) <= MERGE_TOLERANCE_MIN:
                match += 1
            else:
                conflict += 1
    return match, conflict


def _merge(trains: list[Train], diag: Diagnostics) -> list[Train]:
    """Fold trips from later files into matching trips from earlier files."""
    result: list[Train] = []
    by_key: dict[tuple[str, str], list[Train]] = {}
    for t in trains:
        file = t.sources[0].split("#")[0]
        candidates = [m for m in by_key.get((t.number, t.direction), [])
                      if file not in {s.split("#")[0] for s in m.sources}]
        best = None
        if candidates:
            scored = sorted(candidates, key=lambda m: _agreement(m, t), reverse=True)
            match, conflict = _agreement(scored[0], t)
            if match > 0 and conflict == 0:
                best = scored[0]
            elif match > 0:
                best = scored[0]
                diag.add("merge-time-conflict", f"{t.number} {t.direction}",
                         f"{conflict} station(s) differ by >{MERGE_TOLERANCE_MIN} min "
                         f"({best.sources} / {t.sources})")
            elif len(t.stops) <= 1:
                # A lone time on the main sheet for a train timed in full on
                # another sheet (93014 VR 12:45 vs Dahanu sheet 12:50).
                best = scored[0]
                diag.add("merge-single-stop-fragment", f"{t.number} {t.direction}",
                         f"{t.sources} folded into {best.sources}")
        if best is None:
            by_key.setdefault((t.number, t.direction), []).append(t)
            result.append(t)
            continue
        have = {s.station_code: s for s in best.stops}
        for s in t.stops:
            if s.station_code in have:
                if have[s.station_code].time_min != s.time_min:
                    diag.add("merge-minute-difference", f"{t.number} {s.station_code}",
                             f"kept {have[s.station_code].time_min}, other sheet {s.time_min}")
            else:
                best.stops.append(s)
        best.origin = best.origin or t.origin
        best.destination = best.destination or t.destination
        best.cars = best.cars or t.cars
        best.operator = best.operator or t.operator
        have_ext = {(s.station_code, tuple(s.markers)) for s in best.external_stops}
        best.external_stops += [s for s in t.external_stops if (s.station_code, tuple(s.markers)) not in have_ext]
        best.is_ac = best.is_ac or t.is_ac
        best.ac_weekdays_only = best.ac_weekdays_only or t.ac_weekdays_only
        best.ladies_special = best.ladies_special or t.ladies_special
        if best.service.days == "1111111":
            best.service = t.service
        best.notes += [n for n in t.notes if n not in best.notes]
        best.unrecognized_notes += [n for n in t.unrecognized_notes if n not in best.unrecognized_notes]
        best.pass_marks += [p for p in t.pass_marks if p not in best.pass_marks]
        best.sources += t.sources
    return result


def _finalise(train: Train, stations: StationTable, diag: Diagnostics) -> None:
    order = {s.code: s.seq for s in stations.ordered}
    tag = f"{train.number}{'/' + str(train.variant) if train.variant else ''} {train.direction}"
    # Station order is the reliable key across merged sheets; raw clock times
    # can wrap past midnight.
    train.stops.sort(key=lambda s: order[s.station_code], reverse=train.direction == "UP")
    ext_origin = [s for s in train.external_stops if "origin" in s.markers]
    ext_dest = [s for s in train.external_stops if "destination" in s.markers]
    if len(ext_origin) > 1 or len(ext_dest) > 1:
        diag.add("external-terminal-repeated", tag, str([s.station_label for s in train.external_stops]))
    train.external_stops = ext_origin[:1] + ext_dest[:1]
    whole = ext_origin[:1] + train.stops + ext_dest[:1]
    _normalise_times(whole)
    _fix_twelve_hour_slips(whole, tag, diag)
    times = [s.time_min for s in whole]
    if any(b < a for a, b in zip(times, times[1:])):
        diag.add("times-not-monotonic", tag, " ".join(f"{s.station_code}={s.time_min}" for s in whole))
    if ext_origin:
        train.origin = ext_origin[0].station_code
    if ext_dest:
        train.destination = ext_dest[0].station_code
    if len(train.stops) < 2:
        diag.add("train-too-few-stops", tag, str(len(train.stops)))
    if not train.stops:
        return

    first, last = train.stops[0].station_code, train.stops[-1].station_code
    # The header names the terminal; when its cell is blank the train still
    # runs there, so the header wins and the gap is recorded.
    for end, stop_code, attr in ((train.origin, first, "origin"), (train.destination, last, "destination")):
        if end and end not in order:  # off-line terminal (CSMT): nothing to check here
            continue
        if end and end != stop_code:
            beyond = (order[end] > order[stop_code]) == ((attr == "destination") == (train.direction == "DN"))
            if beyond:
                train.terminal_without_time = end
                diag.add("terminal-without-time", tag, f"{attr} {end}, last timed stop {stop_code}")
            else:
                diag.add("terminal-mismatch", tag, f"header {attr} {end} vs stop {stop_code}")
                setattr(train, attr, stop_code)
    train.origin = train.origin or first
    train.destination = train.destination or last

    seqs = sorted(order[s.station_code] for s in train.stops)
    span = {s.code for s in stations.ordered if seqs[0] <= s.seq <= seqs[-1]}
    train.is_fast = len(span - {s.station_code for s in train.stops}) > 0


def parse_dir(pdf_dir: Path, diag: Diagnostics, exclude: frozenset[str] = frozenset()) -> list[Train]:
    """Parse every PDF in a release directory, except file names in `exclude`."""
    return parse_files([p for p in sorted(pdf_dir.glob("*.pdf")) if p.name not in exclude], diag)


def parse_files(paths: list[Path], diag: Diagnostics) -> list[Train]:
    stations = StationTable(LINE)
    raw: list[Train] = []
    for path in paths:
        raw += parse_pdf(path, stations, diag)
    trains = _merge(raw, diag)
    for t in trains:
        _finalise(t, stations, diag)
    trains.sort(key=lambda t: (t.direction, t.stops[0].time_min if t.stops else 0, t.number))
    # Variants are assigned on the merged trips, earliest departure first, so
    # (number, direction, variant) is a stable identity.
    seen: dict[tuple[str, str], int] = {}
    for t in trains:
        key = (t.number, t.direction)
        t.variant = seen.get(key, 0)
        seen[key] = t.variant + 1
    for (number, direction), n in seen.items():
        if n > 1:
            diag.add("number-shared-by-trips", f"{number} {direction}", f"{n} trips")
    return trains
