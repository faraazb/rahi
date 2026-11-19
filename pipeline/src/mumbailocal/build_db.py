"""Write parsed trains into the app's SQLite schema.

The parsers never touch SQL; this module is the only writer. Times are stored
as integer minutes after midnight of the service day (>= 1440 = after
midnight), so "next trains" queries are plain integer comparisons.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .model import Train
from .stations import StationTable, all_codes

# 3: stop_time.arr_min, stop_time.pos and line_station.ord (additive; a v2 reader still works).
SCHEMA_VERSION = 3

LINES = {
    # code: (name, colour)
    "WR": ("Western", "#E2231A"),
    "CR": ("Central", "#F4B400"),
    "HR": ("Harbour", "#1E88E5"),
    "THR": ("Trans-Harbour", "#00897B"),
    "UR": ("Port (Uran)", "#8E24AA"),
    "PUNE": ("Pune–Lonavala", "#6D4C41"),
    "DVP": ("Vasai–Diva–Panvel", "#C2185B"),
    "NM": ("Neral–Matheran", "#2E7D32"),
}

SCHEMA = """
CREATE TABLE line (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  color TEXT
);
CREATE TABLE station (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  code_source TEXT
);
CREATE TABLE line_station (
  line_id INTEGER NOT NULL REFERENCES line(id),
  station_id INTEGER NOT NULL REFERENCES station(id),
  seq INTEGER NOT NULL,            -- stations from the line's root (equal on parallel branches)
  ord INTEGER NOT NULL,            -- display order: the trunk, then each branch
  PRIMARY KEY (line_id, station_id)
);
CREATE TABLE service (
  id INTEGER PRIMARY KEY,
  days TEXT NOT NULL,             -- Mon..Sun flags, e.g. 1111110
  not_on_holidays INTEGER NOT NULL,
  UNIQUE (days, not_on_holidays)
);
CREATE TABLE train (
  id INTEGER PRIMARY KEY,
  number TEXT NOT NULL,
  variant INTEGER NOT NULL DEFAULT 0,
  line_id INTEGER NOT NULL REFERENCES line(id),
  direction INTEGER NOT NULL,     -- 1 up, 2 down
  is_fast INTEGER,
  is_ac INTEGER NOT NULL,
  ac_weekdays_only INTEGER NOT NULL,
  ladies_special INTEGER NOT NULL,
  cars INTEGER,
  service_id INTEGER NOT NULL REFERENCES service(id),
  origin_station_id INTEGER REFERENCES station(id),
  dest_station_id INTEGER REFERENCES station(id),
  dest_time_missing INTEGER NOT NULL DEFAULT 0,  -- terminal printed without a time
  operator TEXT,  -- set when another railway runs the train (e.g. CR Harbour on WR)
  notes TEXT
);
CREATE TABLE stop_time (
  train_id INTEGER NOT NULL REFERENCES train(id),
  seq INTEGER NOT NULL,
  station_id INTEGER NOT NULL REFERENCES station(id),
  time_min INTEGER NOT NULL,       -- departure (arrival at the last stop)
  platform TEXT,
  arr_min INTEGER,                 -- arrival, only where the source gives one apart from time_min
  pos INTEGER NOT NULL,            -- stations along the train's route from its first stop,
                                   -- so pos(b) - pos(a) > seq(b) - seq(a) (stop seq) means it skips stations
  PRIMARY KEY (train_id, seq)
);
CREATE INDEX ix_stop_station_time ON stop_time(station_id, time_min);
CREATE INDEX ix_train_line_dir ON train(line_id, direction);
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


EXTERNAL_NAMES = {"CSMT": "Chhatrapati Shivaji Maharaj Terminus", "PNVL": "Panvel"}


def _external_name(code: str) -> str:
    return EXTERNAL_NAMES.get(code) or all_codes().get(code, code)


def _travel_order(t: Train) -> list:
    origin = [s for s in t.external_stops if "origin" in s.markers]
    dest = [s for s in t.external_stops if "destination" in s.markers]
    return origin + t.stops + dest


def _route_positions(stops: list, table: StationTable) -> list[int]:
    """Stations travelled from the first stop, along the track graph. A stop
    off the line (an external terminal) counts as one station on."""
    pos = [0]
    for a, b in zip(stops, stops[1:]):
        p = table.path(a.station_code, b.station_code) if \
            a.station_code in table.by_code and b.station_code in table.by_code else None
        pos.append(pos[-1] + (len(p) - 1 if p else 1))
    return pos


def build(out: Path, trains_by_line: dict[str, list[Train]], meta: dict[str, str]) -> None:
    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(out)
    db.executescript(SCHEMA)

    # Every line's own stations first, so a station shared by two lines (CSMT
    # on CR and Harbour) is never first created as another line's off-line
    # terminal.
    station_ids: dict[str, int] = {}
    line_ids: dict[str, int] = {}
    for line_code in trains_by_line:
        name, color = LINES[line_code]
        line_ids[line_code] = db.execute(
            "INSERT INTO line(code, name, color) VALUES (?,?,?)", (line_code, name, color)
        ).lastrowid
        for ord_, st in enumerate(StationTable(line_code).rows, 1):
            if st.code not in station_ids:
                station_ids[st.code] = db.execute(
                    "INSERT INTO station(code, name, code_source) VALUES (?,?,?)",
                    (st.code, st.name, st.code_source),
                ).lastrowid
            db.execute(
                "INSERT INTO line_station(line_id, station_id, seq, ord) VALUES (?,?,?,?)",
                (line_ids[line_code], station_ids[st.code], st.seq, ord_),
            )

    for line_code, trains in trains_by_line.items():
        line_id = line_ids[line_code]
        table = StationTable(line_code)
        # Off-line terminals (Borivali for a Harbour train timed on to WR)
        # without a line_station row when their own line is not loaded.
        for t in trains:
            for s in t.external_stops:
                if s.station_code not in station_ids:
                    station_ids[s.station_code] = db.execute(
                        "INSERT INTO station(code, name, code_source) VALUES (?,?,?)",
                        (s.station_code, _external_name(s.station_code), "external"),
                    ).lastrowid

        for t in trains:
            if not t.stops:
                continue
            db.execute(
                "INSERT OR IGNORE INTO service(days, not_on_holidays) VALUES (?,?)",
                (t.service.days, int(t.service.not_on_holidays)),
            )
            service_id = db.execute(
                "SELECT id FROM service WHERE days=? AND not_on_holidays=?",
                (t.service.days, int(t.service.not_on_holidays)),
            ).fetchone()[0]
            train_id = db.execute(
                """INSERT INTO train(number, variant, line_id, direction, is_fast, is_ac,
                   ac_weekdays_only, ladies_special, cars, service_id, origin_station_id,
                   dest_station_id, dest_time_missing, operator, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    t.number, t.variant, line_id, 1 if t.direction == "UP" else 2,
                    None if t.is_fast is None else int(t.is_fast), int(t.is_ac),
                    int(t.ac_weekdays_only), int(t.ladies_special), t.cars, service_id,
                    station_ids.get(t.origin or ""), station_ids.get(t.destination or ""),
                    int(t.terminal_without_time is not None),
                    t.operator,
                    "; ".join(t.notes) or None,
                ),
            ).lastrowid
            stops = _travel_order(t)
            db.executemany(
                "INSERT INTO stop_time(train_id, seq, station_id, time_min, arr_min, pos) VALUES (?,?,?,?,?,?)",
                [(train_id, i, station_ids[s.station_code], s.time_min, s.arr_min, pos)
                 for i, (s, pos) in enumerate(zip(stops, _route_positions(stops, table)))],
            )

    meta = {"schema_version": str(SCHEMA_VERSION),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **meta}
    db.executemany("INSERT INTO meta(key, value) VALUES (?,?)", meta.items())
    db.commit()
    db.execute("VACUUM")
    db.close()
