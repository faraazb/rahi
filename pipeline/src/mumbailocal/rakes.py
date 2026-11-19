"""Which trip a rake works next, from Yatri's rake links.

LOCAL ONLY, like `platforms.py`: no official source publishes rake workings
(the CR sheets' "A 11" / "PL 5" codes label one train each, they do not chain),
so this comes from the database bundled in the Yatri app and is refused by a
public release (`release.LOCAL_ONLY_TABLES`).

    rake_next(train_id, next_train_id)

means the rake that arrives as `train_id` leaves again as `next_train_id`. The
app uses it for "board earlier, stay on": a train heading into a terminus that
turns there and comes back as the train you want.

Yatri lists each rake's day as `rake_link_code` + `rake_link_order_no`.
Consecutive entries are matched onto our trains by number, and a link is kept
only when our own timetable agrees with it: the first trip ends where the next
one starts, the next one leaves within `MAX_TURN_MINUTES`, and the two run on
at least one common day. Anything else (renumbered trains, a chain that skips
a trip, a terminus we model differently) is dropped, never guessed.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass

MIN_TURN_MINUTES = 1
MAX_TURN_MINUTES = 120

# Gate: hold the layer back when too few of Yatri's links check out.
MIN_AGREEMENT = 0.8

SCHEMA = """
CREATE TABLE rake_next (
  train_id INTEGER PRIMARY KEY REFERENCES train(id),
  next_train_id INTEGER NOT NULL REFERENCES train(id)
);
"""


@dataclass
class Stats:
    yatri_links: int = 0
    linked: int = 0
    no_train: int = 0
    other_station: int = 0
    bad_gap: int = 0
    no_common_day: int = 0
    ambiguous: int = 0

    @property
    def agreement(self) -> float:
        """Share of Yatri links between trains we have that our timetable confirms."""
        tested = self.yatri_links - self.no_train
        return self.linked / tested if tested else 0.0

    def as_dict(self) -> dict:
        return {**asdict(self), "agreement": round(self.agreement, 4)}


@dataclass
class _Trip:
    id: int
    first: int
    first_time: int
    last: int
    last_time: int
    days: str


def _trips(ours: sqlite3.Connection) -> dict[str, list[_Trip]]:
    by_number: dict[str, list[_Trip]] = defaultdict(list)
    for tid, number, days, first, first_time, last, last_time in ours.execute(
        """SELECT t.id, t.number, sv.days,
                  f.station_id, f.time_min, l.station_id, COALESCE(l.arr_min, l.time_min)
             FROM train t
             JOIN service sv ON sv.id = t.service_id
             JOIN stop_time f ON f.train_id = t.id AND f.seq = (SELECT MIN(seq) FROM stop_time WHERE train_id = t.id)
             JOIN stop_time l ON l.train_id = t.id AND l.seq = (SELECT MAX(seq) FROM stop_time WHERE train_id = t.id)"""):
        by_number[number].append(_Trip(tid, first, first_time, last, last_time, days))
    return by_number


def match(ours: sqlite3.Connection, yatri: sqlite3.Connection) -> tuple[list[tuple[int, int]], Stats]:
    stats = Stats()
    trips = _trips(ours)
    chain = yatri.execute(
        """SELECT number, rake_link_code, rake_link_order_no FROM local_trains
            WHERE rake_link_code IS NOT NULL AND rake_link_code NOT IN ('', 'NULL')
              AND (deleted_at IS NULL OR deleted_at = 'NULL')
            ORDER BY rake_link_code, rake_link_order_no""").fetchall()
    links: dict[int, int] = {}
    for (a_num, a_code, a_ord), (b_num, b_code, b_ord) in zip(chain, chain[1:]):
        if a_code != b_code or b_ord != a_ord + 1:
            continue
        stats.yatri_links += 1
        A, B = trips.get(a_num, []), trips.get(b_num, [])
        if not A or not B:
            stats.no_train += 1
            continue
        found, reason = [], "other_station"
        for a in A:
            for b in B:
                if a.last != b.first:
                    continue
                gap = (b.first_time - a.last_time) % 1440
                if not MIN_TURN_MINUTES <= gap <= MAX_TURN_MINUTES:
                    reason = "bad_gap"
                    continue
                if not any(x == y == "1" for x, y in zip(a.days, b.days)):
                    reason = "no_common_day" if reason != "bad_gap" else reason
                    continue
                found.append((a.id, b.id))
        # Number variants (weekday / Sunday copies) can each link to their own copy.
        sources = defaultdict(list)
        for a_id, b_id in found:
            sources[a_id].append(b_id)
        if not found:
            setattr(stats, reason, getattr(stats, reason) + 1)
            continue
        if any(len(v) > 1 for v in sources.values()):
            stats.ambiguous += 1
            continue
        stats.linked += 1
        for a_id, (b_id,) in sources.items():
            links[a_id] = b_id
    return sorted(links.items()), stats


def write(ours: sqlite3.Connection, rows: list[tuple[int, int]]) -> None:
    """Replace the `rake_next` table in `ours` (the caller commits)."""
    ours.execute("DROP TABLE IF EXISTS rake_next")
    ours.executescript(SCHEMA)
    ours.executemany("INSERT INTO rake_next VALUES (?,?)", rows)
