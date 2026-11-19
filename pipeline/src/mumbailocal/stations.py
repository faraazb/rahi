"""Curated station tables (data/stations/<line>.csv) and label normalisation.

Timetable PDFs spell the same station many ways ("M'BAI CENTRAL (L)",
"MUM'AI CENTRAL(L)", "Kandivli"/"Kandivali", letter-spaced "N a ll a S o p a r a").
Labels are reduced to upper-case alphanumerics before lookup, so only genuine
spelling differences need an alias entry in the CSV.

Lines with branches (CR Kalyan -> Karjat / Kasara, Harbour Vadala -> Goregaon /
Panvel) list each branch after the trunk. The optional `prev` column names a
station's neighbour towards the line's root (the first row): blank means the
row above, "A|B" several (two branches joining), "-" none (a second root).
`seq` is the station's distance in stations from the root, so on any one
route the difference in seq is the number of hops (the app relies on this).
"""

from __future__ import annotations

import csv
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from . import paths

DATA_DIR = paths.DATA_DIR / "stations"


def norm(label: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", label.upper())


@dataclass(frozen=True)
class Station:
    seq: int
    code: str
    name: str
    code_source: str


class StationTable:
    def __init__(self, line: str, path: Path | None = None):
        self.line = line
        path = path or DATA_DIR / f"{line.lower()}.csv"
        self.ordered: list[Station] = []
        # As listed in the CSV: the trunk, then each branch in turn (for display).
        self.rows: list[Station] = []
        self._by_alias: dict[str, Station] = {}
        self._names: dict[str, Station] = {}
        self.by_code: dict[str, Station] = {}
        # Undirected track graph; a line without `prev` is one straight run.
        self.neighbours: dict[str, set[str]] = {}
        previous_row: Station | None = None
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                s = Station(int(r["seq"]), r["code"], r["name"], r["code_source"])
                if s.code in self.by_code:
                    raise ValueError(f"{path.name}: station {s.code} listed twice")
                self.ordered.append(s)
                self.rows.append(s)
                self.by_code[s.code] = s
                self.neighbours[s.code] = set()
                prev = (r.get("prev") or "").strip()
                links = [] if prev == "-" else prev.split("|") if prev else \
                    [previous_row.code] if previous_row else []
                for p in links:
                    if p not in self.by_code:
                        raise ValueError(f"{path.name}: {s.code} follows unknown station {p}")
                    self.neighbours[s.code].add(p)
                    self.neighbours[p].add(s.code)
                previous_row = s
                for alias in [s.name, s.code, *r["aliases"].split("|")]:
                    key = norm(alias)
                    if key in self._by_alias and self._by_alias[key] != s:
                        raise ValueError(f"alias {alias!r} maps to two stations")
                    self._by_alias[key] = s
                    if alias != s.code:  # loose matching never uses bare codes
                        self._names[key] = s
        self.root = self.ordered[0].code
        self.ordered.sort(key=lambda s: s.seq)

    def path(self, a: str, b: str) -> list[str] | None:
        """Stations from a to b along the track, both included (shortest route)."""
        came: dict[str, str | None] = {a: None}
        todo = deque([a])
        while todo:
            cur = todo.popleft()
            if cur == b:
                out = [b]
                while came[out[-1]] is not None:
                    out.append(came[out[-1]])
                return out[::-1]
            for n in sorted(self.neighbours[cur]):
                if n not in came:
                    came[n] = cur
                    todo.append(n)
        return None

    def hops_from_root(self, code: str) -> int:
        p = self.path(self.root, code)
        return len(p) - 1 if p else -1

    def lookup(self, label: str) -> Station | None:
        return self.match(label)[0]

    def match(self, label: str) -> tuple[Station | None, str]:
        """(station, how) where how is "exact", "qualifier", "prefix", "typo" or "".

        Only "exact" is certain. The others keep a sheet usable when a new
        release truncates or misspells a name, and callers should report them
        so the CSV gains a proper alias.
        """
        key = norm(label)
        if not key:
            return None, ""
        if s := self._by_alias.get(key):
            return s, "exact"
        # Trailing qualifiers printed in the label column: arrival/departure
        # markers ("CHURCHGATE D"), car-shed and origin notes ("Grant Road C/S",
        # "Charni Road EX VR").
        stripped = _QUALIFIERS.sub("", label.strip())
        if stripped != label.strip() and (s := self._names.get(norm(stripped))):
            return s, "qualifier"
        # Truncated names ("CHURCHGAT", "M'BAI CENTR").
        if len(key) >= 5:
            hits = {s for k, s in self._names.items() if k.startswith(key)}
            if len(hits) == 1:
                return hits.pop(), "prefix"
        # One-letter slips in long names ("Ville Parle").
        if len(key) >= 8:
            hits = {s for k, s in self._names.items() if abs(len(k) - len(key)) <= 1 and _within_one_edit(k, key)}
            if len(hits) == 1:
                return hits.pop(), "typo"
        return None, ""


def all_codes() -> dict[str, str]:
    """Every station code in data/stations/*.csv -> its name."""
    out: dict[str, str] = {}
    for path in sorted(DATA_DIR.glob("*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out.setdefault(r["code"], r["name"])
    return out


_QUALIFIERS = re.compile(r"(\s+(EX\.?\s+[A-Z]{2,5}|C/S|[AD]))+$", re.IGNORECASE)


def _within_one_edit(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return a[i:] == b[i + 1:]
