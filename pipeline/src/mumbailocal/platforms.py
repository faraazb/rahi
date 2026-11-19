"""Platform numbers and door sides, matched onto our timetable from Yatri.

LOCAL ONLY. No official source publishes platforms, so this layer is built
from the database bundled in the Yatri app (CDP India / Central Railway).
Until redistribution is agreed with them, it is added only to local builds;
`release.make_release` refuses a database that carries it unless told the
release is local (see `LOCAL_ONLY_TABLES`).

    platform(train_id, seq, platform, door_side, door_side_raw)
    rake_next(train_id, next_train_id)      -- see rakes.py

keyed by our own stop (train id + stop sequence), so the app joins it
directly onto `stop_time`. A stop gets a platform only when Yatri has the
same train number calling at the same station within `MAX_MINUTES_APART`,
so a renumbered or retimed train never inherits another train's platform.

Yatri files trains by its own lines (WR's Harbour trains sit under its
Harbour line), so trains are matched by number across all of Yatri's lines.

Door side (LEFT/RIGHT/BOTH, relative to the direction of travel) is less
reliable than the platform: the same platform and direction sometimes carries
both values. `door_side` is set only when one value clearly dominates for that
station, platform and direction (`DOOR_SIDE_AGREEMENT`); the raw value is
kept in `door_side_raw` for checking.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import rakes
from .stations import StationTable

MAX_MINUTES_APART = 2
DOOR_SIDE_AGREEMENT = 0.9
DOOR_SIDE_MIN_TRAINS = 3
SIDES = {"LEFT", "RIGHT", "BOTH"}
PLATFORM_RE = re.compile(r"^\d{1,2}[A-Z]?(,\d{1,2}[A-Z]?)*$")

# Gate: hold the layer back when coverage is low or drops against the last build.
MIN_COVERAGE = 0.85
MAX_COVERAGE_DROP = 0.05

SCHEMA = """
CREATE TABLE platform (
  train_id INTEGER NOT NULL REFERENCES train(id),
  seq INTEGER NOT NULL,
  platform TEXT NOT NULL,   -- "4", or "1,2" meaning one of these
  door_side TEXT,           -- LEFT / RIGHT / BOTH, only when consistent for the platform
  door_side_raw TEXT,       -- Yatri's value for this stop, normalised
  PRIMARY KEY (train_id, seq)
);
"""


def norm(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def norm_platform(p: str | None) -> str | None:
    p = re.sub(r"\s+", "", (p or "").upper()).strip(",")
    return p if p and PLATFORM_RE.match(p) else None


def norm_side(s: str | None) -> str | None:
    s = (s or "").strip().upper()
    return s if s in SIDES else None


@dataclass
class Stats:
    stops: int = 0
    matched: int = 0
    no_train: int = 0
    no_stop: int = 0
    no_platform: int = 0
    bad_platform: int = 0
    time_mismatch: int = 0
    door_side_set: int = 0
    door_side_groups: int = 0
    door_side_conflicting_groups: int = 0
    unmapped_stations: list[str] = field(default_factory=list)
    weakest_stations: list[tuple[str, float, int]] = field(default_factory=list)
    rakes: dict = field(default_factory=dict)  # rakes.Stats.as_dict()

    @property
    def coverage(self) -> float:
        return self.matched / self.stops if self.stops else 0.0

    def as_dict(self) -> dict:
        return {**asdict(self), "coverage": round(self.coverage, 4)}


@dataclass
class Verdict:
    ok: bool
    reasons: list[str]

    def __str__(self) -> str:
        return "OK" if self.ok else "HOLD: " + "; ".join(self.reasons)


def _minutes_apart(a: int, b: int) -> int:
    d = (a - b) % 1440
    return min(d, 1440 - d)


def match(ours: sqlite3.Connection, yatri: sqlite3.Connection) -> tuple[list[tuple], Stats]:
    """Rows for the `platform` table, and how well the two sources lined up."""
    stats = Stats()
    our_by_name: dict[str, set[int]] = defaultdict(set)
    for sid, name in ours.execute("SELECT id, name FROM station"):
        our_by_name[norm(name)].add(sid)
    our_by_code = {code: sid for sid, code in ours.execute("SELECT id, code FROM station")}
    our_code = {sid: code for code, sid in our_by_code.items()}
    tables = [StationTable(line) for (line,) in ours.execute("SELECT code FROM line")]

    # One Yatri station can be several of ours: Yatri has a single "Dadar",
    # we keep WR's DDR and CR's DR apart. A train calls at only one of them.
    to_ours: dict[str, set[int]] = {}
    for ls_id, code, name in yatri.execute("SELECT ls_id, code, name FROM local_stations WHERE deleted_at IS NULL OR deleted_at = 'NULL'"):
        sids = set(our_by_name.get(norm(name), set()))
        for table in tables:  # exact alias matches only ("Nava Sheva")
            st, how = table.match(name)
            if st is not None and how == "exact" and st.code in our_by_code:
                sids.add(our_by_code[st.code])
        if not sids and code in our_by_code:
            sids.add(our_by_code[code])
        if sids:
            to_ours[str(ls_id)] = sids

    theirs: dict[tuple[str, int], tuple[int, str | None, str | None]] = {}
    numbers: set[str] = set()
    for num, ls_id, tm, pf, side in yatri.execute(
        """SELECT s.local_train_number, s.station_id, s.time, s.platform_number, s.platform_direction
             FROM local_train_schedule s
             JOIN local_trains t ON t.number = s.local_train_number
            WHERE (s.deleted_at IS NULL OR s.deleted_at = 'NULL')
              AND (t.deleted_at IS NULL OR t.deleted_at = 'NULL')"""):
        numbers.add(num)
        h, m = map(int, str(tm).split(":")[:2])
        for sid in to_ours.get(str(ls_id), ()):
            theirs[(num, sid)] = (h * 60 + m, pf, side)

    rows: list[list] = []
    per_station: dict[int, Counter] = defaultdict(Counter)
    for train_id, number, direction, seq, sid, time_min in ours.execute(
        """SELECT t.id, t.number, t.direction, st.seq, st.station_id, st.time_min
             FROM stop_time st JOIN train t ON t.id = st.train_id
            ORDER BY t.id, st.seq"""):
        stats.stops += 1
        hit = theirs.get((number, sid))
        if number not in numbers:
            stats.no_train += 1
            outcome = "miss"
        elif hit is None:
            stats.no_stop += 1
            outcome = "miss"
        elif _minutes_apart(time_min, hit[0]) > MAX_MINUTES_APART:
            stats.time_mismatch += 1
            outcome = "miss"
        elif not (hit[1] or "").strip():
            stats.no_platform += 1
            outcome = "miss"
        elif (pf := norm_platform(hit[1])) is None:
            stats.bad_platform += 1
            outcome = "miss"
        else:
            stats.matched += 1
            outcome = "ok"
            rows.append([train_id, seq, pf, None, norm_side(hit[2]), sid, direction])
        per_station[sid][outcome] += 1

    # Door side: one value per (station, platform, direction) when it clearly dominates.
    groups: dict[tuple, Counter] = defaultdict(Counter)
    for r in rows:
        if r[4]:
            groups[(r[5], r[2], r[6])][r[4]] += 1
    agreed: dict[tuple, str] = {}
    for key, c in groups.items():
        side, n = c.most_common(1)[0]
        total = sum(c.values())
        if len(c) > 1:
            stats.door_side_conflicting_groups += 1
        if total >= DOOR_SIDE_MIN_TRAINS and n / total >= DOOR_SIDE_AGREEMENT:
            agreed[key] = side
    stats.door_side_groups = len(groups)
    for r in rows:
        r[3] = agreed.get((r[5], r[2], r[6]))
        stats.door_side_set += r[3] is not None

    # Our stations no Yatri station maps to (by name or code): they can never get a platform.
    mapped = set().union(*to_ours.values())
    stats.unmapped_stations = sorted(our_code[sid] for sid in per_station if sid not in mapped)
    stats.weakest_stations = sorted(
        ((our_code[sid], round(c["ok"] / sum(c.values()), 3), sum(c.values())) for sid, c in per_station.items()),
        key=lambda x: (x[1], x[0]))[:10]
    return [tuple(r[:5]) for r in rows], stats


def check(stats: Stats, previous: dict | None) -> Verdict:
    reasons = []
    if stats.coverage < MIN_COVERAGE:
        reasons.append(f"coverage {stats.coverage:.1%} is below {MIN_COVERAGE:.0%}")
    if previous and previous.get("coverage") is not None:
        drop = previous["coverage"] - stats.coverage
        if drop > MAX_COVERAGE_DROP:
            reasons.append(f"coverage fell {drop:.1%} since the last build ({previous['coverage']:.1%} -> {stats.coverage:.1%})")
    tested = stats.rakes.get("yatri_links", 0) - stats.rakes.get("no_train", 0)
    if tested and stats.rakes["agreement"] < rakes.MIN_AGREEMENT:
        reasons.append(f"only {stats.rakes['agreement']:.1%} of Yatri's rake links match our timetable "
                       f"(need {rakes.MIN_AGREEMENT:.0%})")
    return Verdict(not reasons, reasons)


def add_to_db(db_path: Path, yatri_path: Path, source_meta: dict[str, str] | None = None,
              previous: dict | None = None, strict: bool = False) -> tuple[Stats, Verdict]:
    """Match, gate, and (unless held under strict) replace the `platform` and `rake_next` tables."""
    ours = sqlite3.connect(db_path)
    yatri = sqlite3.connect(f"file:{yatri_path}?mode=ro", uri=True)
    try:
        rows, stats = match(ours, yatri)
        rake_rows, rake_stats = rakes.match(ours, yatri)
        stats.rakes = rake_stats.as_dict()
        verdict = check(stats, previous)
        if strict and not verdict.ok:
            return stats, verdict
        ours.execute("DROP TABLE IF EXISTS platform")
        ours.executescript(SCHEMA)
        ours.executemany("INSERT INTO platform VALUES (?,?,?,?,?)", rows)
        rakes.write(ours, rake_rows)
        ours.execute("DELETE FROM meta WHERE key LIKE 'platforms_%'")
        meta = {"platforms_source": "yatri", "platforms_local_only": "1",
                "platforms_coverage": f"{stats.coverage:.4f}",
                "platforms_rake_agreement": f"{rake_stats.agreement:.4f}", **(source_meta or {})}
        ours.executemany("INSERT INTO meta(key, value) VALUES (?,?)",
                         [(k if k.startswith("platforms_") else f"platforms_{k}", str(v)) for k, v in meta.items()])
        ours.commit()
        ours.execute("VACUUM")
        return stats, verdict
    finally:
        ours.close()
        yatri.close()


def load_stats(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None
