"""The local-only platforms layer: matching rules, door-side agreement, the
gate, and the release guard that keeps it out of public releases."""

import json
import sqlite3

import pytest

from mumbailocal import platforms
from mumbailocal.release import LocalOnlyData, make_release

STATIONS = [(1, "CCG", "Churchgate"), (2, "DDR", "Dadar"), (3, "BVI", "Borivali")]


def make_ours(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE line (id INTEGER PRIMARY KEY, code TEXT, name TEXT, color TEXT);
        CREATE TABLE station (id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, code_source TEXT);
        CREATE TABLE line_station (line_id INTEGER, station_id INTEGER, seq INTEGER);
        CREATE TABLE service (id INTEGER PRIMARY KEY, days TEXT, not_on_holidays INTEGER);
        CREATE TABLE train (id INTEGER PRIMARY KEY, number TEXT, line_id INTEGER, direction INTEGER,
                            service_id INTEGER DEFAULT 1);
        CREATE TABLE stop_time (train_id INTEGER, seq INTEGER, station_id INTEGER, time_min INTEGER, platform TEXT,
                                arr_min INTEGER);
        INSERT INTO service VALUES (1, '1111111', 0), (2, '0000001', 0);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO line VALUES (1, 'WR', 'Western', NULL);
        INSERT INTO meta VALUES ('schema_version', '2');
    """)
    db.executemany("INSERT INTO station(id, code, name) VALUES (?,?,?)", STATIONS)
    db.executemany("INSERT INTO line_station VALUES (1,?,?)", [(s, s) for s, _, _ in STATIONS])
    # Down trains CCG -> DDR -> BVI, ten minutes apart, 08:00, 08:10, ...
    for i in range(5):
        db.execute("INSERT INTO train(id, number, line_id, direction) VALUES (?,?,1,2)", (i + 1, f"9000{i}"))
        db.executemany("INSERT INTO stop_time(train_id, seq, station_id, time_min) VALUES (?,?,?,?)",
                       [(i + 1, k, sid, 480 + 10 * i + 15 * k) for k, sid in enumerate((1, 2, 3))])
    db.commit()
    return db


def make_yatri(path, overrides=None):
    """Yatri's copy of the same trains. Its station codes differ (D for Dadar)."""
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE local_stations (ls_id TEXT, code TEXT, name TEXT, deleted_at TEXT);
        CREATE TABLE local_trains (number TEXT, line_id TEXT, deleted_at TEXT,
                                   rake_link_code TEXT, rake_link_order_no INTEGER);
        CREATE TABLE local_train_schedule (local_train_number TEXT, station_id TEXT, time TEXT,
                                           platform_number TEXT, platform_direction TEXT, deleted_at TEXT);
        INSERT INTO local_stations VALUES ('11', 'CCG', 'Churchgate', NULL), ('12', 'D', 'DADAR', NULL),
                                          ('13', 'BVI', 'Borivali', 'NULL');
    """)
    overrides = overrides or {}
    for i in range(5):
        num = f"9000{i}"
        db.execute("INSERT INTO local_trains(number, line_id, deleted_at) VALUES (?, '3', NULL)", (num,))  # filed under another line
        for k, ls in enumerate(("11", "12", "13")):
            m = 480 + 10 * i + 15 * k
            pf, side = overrides.get((num, ls), ("2", "Left" if ls == "12" else "RIGHT"))
            db.execute("INSERT INTO local_train_schedule VALUES (?,?,?,?,?,NULL)",
                       (num, ls, f"{m // 60:02d}:{m % 60:02d}", pf, side))
    db.commit()
    return db


@pytest.fixture
def dbs(tmp_path):
    ours, yatri = tmp_path / "ours.sqlite", tmp_path / "yatri.db"
    make_ours(ours).close()
    return ours, yatri


def rows_of(path):
    db = sqlite3.connect(path)
    try:
        return {(t, s): (p, d, r) for t, s, p, d, r in db.execute("SELECT * FROM platform")}
    finally:
        db.close()


def test_matches_by_number_and_station_name_across_lines(dbs):
    ours, yatri = dbs
    make_yatri(yatri).close()
    stats, verdict = platforms.add_to_db(ours, yatri)
    assert verdict.ok and stats.matched == stats.stops == 15
    rows = rows_of(ours)
    assert rows[(1, 0)] == ("2", "RIGHT", "RIGHT")  # Churchgate
    assert rows[(3, 1)][1] == "LEFT"  # 'Left' normalised; Dadar matched by name despite code D


def test_skips_retimed_blank_and_malformed_platforms(dbs):
    ours, yatri = dbs
    y = make_yatri(yatri, {("90000", "12"): ("", "LEFT"), ("90001", "12"): ("PF-3?", "LEFT"),
                           ("90002", "11"): (" 1, 2 ", "BOTH")})
    # Train 90003 runs 5 minutes later at Dadar in Yatri: a different train, no platform.
    y.execute("UPDATE local_train_schedule SET time = '08:50' WHERE local_train_number = '90003' AND station_id = '12'")
    y.commit()
    y.close()
    stats, _ = platforms.add_to_db(ours, yatri)
    rows = rows_of(ours)
    assert (1, 1) not in rows and stats.no_platform == 1
    assert (2, 1) not in rows and stats.bad_platform == 1
    assert (4, 1) not in rows and stats.time_mismatch == 1
    assert rows[(3, 0)][0] == "1,2"


def test_door_side_only_when_platform_group_agrees(dbs):
    ours, yatri = dbs
    make_yatri(yatri, {("90000", "13"): ("2", "LEFT")}).close()  # 1 of 5 disagrees at Borivali
    stats, _ = platforms.add_to_db(ours, yatri)
    rows = rows_of(ours)
    assert rows[(2, 2)][1:] == (None, "RIGHT")  # 80% agreement is not enough to show
    assert rows[(2, 1)][1] == "LEFT"
    assert stats.door_side_conflicting_groups == 1


def test_gate_holds_low_coverage_and_drops(dbs):
    ours, yatri = dbs
    make_yatri(yatri, {(f"9000{i}", "12"): ("", None) for i in range(5)}).close()
    stats, verdict = platforms.add_to_db(ours, yatri, strict=True)
    assert not verdict.ok and "coverage" in str(verdict)
    with sqlite3.connect(ours) as db:  # strict + HOLD writes nothing
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'platform'").fetchone()
    assert not platforms.check(platforms.Stats(stops=100, matched=90), {"coverage": 0.99}).ok
    assert platforms.check(platforms.Stats(stops=100, matched=97), {"coverage": 0.99}).ok


def test_release_refuses_local_only_layer_unless_local(dbs, tmp_path):
    ours, yatri = dbs
    make_yatri(yatri).close()
    make_release(ours, tmp_path / "rel", tag="plain")  # no layer: fine
    platforms.add_to_db(ours, yatri, {"version": "9.9"})
    with pytest.raises(LocalOnlyData):
        make_release(ours, tmp_path / "rel", tag="public")
    assert not (tmp_path / "rel" / "public").exists()
    rel = make_release(ours, tmp_path / "rel", tag="local", local=True)
    m = json.loads((rel / "manifest.json").read_text())
    assert m["local"] is True and m["layers"]["platform"]["local_only"] is True
    with sqlite3.connect(ours) as db:
        meta = dict(db.execute("SELECT key, value FROM meta"))
    assert meta["platforms_local_only"] == "1" and meta["platforms_version"] == "9.9"


def test_release_merges_layers_only_when_asked(dbs, tmp_path):
    ours, yatri = dbs
    make_yatri(yatri).close()
    platforms.add_to_db(ours, yatri)
    rel = make_release(ours, tmp_path / "rel", tag="merged", merge_layers=True)
    m = json.loads((rel / "manifest.json").read_text())
    assert m["local"] is False and m["layers"]["platform"]["local_only"] is False


# ---------------------------------------------------------------- rake links

def add_turnarounds(ours_path, yatri_path):
    """Up trains back from Borivali, and Yatri chains joining them to the down trains."""
    db = sqlite3.connect(ours_path)
    # 90000 reaches BVI at 08:30 and 90100 leaves BVI at 08:40 (a turn); 90001 reaches 08:40 but
    # 90101 leaves at 11:00 (too long); 90102 runs only on Sundays, which 90002 (daily) shares.
    # 90103 is another down train from Churchgate: 90004 ends at Borivali, so it cannot be its rake.
    for tid, num, start, service, stops in [(11, "90100", 520, 1, (3, 2, 1)), (12, "90101", 660, 1, (3, 2, 1)),
                                            (13, "90102", 560, 2, (3, 2, 1)), (14, "90103", 600, 1, (1, 2, 3))]:
        db.execute("INSERT INTO train(id, number, line_id, direction, service_id) VALUES (?,?,1,?,?)",
                   (tid, num, 1 if stops[0] == 3 else 2, service))
        db.executemany("INSERT INTO stop_time(train_id, seq, station_id, time_min) VALUES (?,?,?,?)",
                       [(tid, k, sid, start + 15 * k) for k, sid in enumerate(stops)])
    db.commit()
    db.close()
    y = sqlite3.connect(yatri_path)
    y.executemany("INSERT INTO local_trains VALUES (?, '3', NULL, ?, ?)", [
        ("90100", "R1", 2), ("90101", "R2", 2), ("90102", "R3", 2), ("90103", "R4", 2), ("90777", "R5", 2)])
    y.executemany("UPDATE local_trains SET rake_link_code = ?, rake_link_order_no = 1 WHERE number = ?", [
        ("R1", "90000"), ("R2", "90001"), ("R3", "90002"), ("R4", "90004"), ("R5", "90003")])
    y.commit()
    y.close()


def test_rake_links_kept_only_when_our_timetable_agrees(dbs):
    ours, yatri = dbs
    make_yatri(yatri).close()
    add_turnarounds(ours, yatri)
    stats, verdict = platforms.add_to_db(ours, yatri)
    with sqlite3.connect(ours) as db:
        links = dict(db.execute("SELECT train_id, next_train_id FROM rake_next"))
    assert links == {1: 11, 3: 13}  # BVI turn in 10 min; Sunday-only next trip shares Sunday
    r = stats.rakes
    assert r["yatri_links"] == 5 and r["linked"] == 2
    assert r["bad_gap"] == 1  # 90001 -> 90101: 2 h 15 min at Borivali
    assert r["other_station"] == 1  # 90004 ends at BVI, 90103 starts at CCG
    assert r["no_train"] == 1  # 90777 is not in our timetable
    # 2 of the 4 links between trains we have is below the gate (written anyway: not strict).
    assert not verdict.ok and "rake links" in str(verdict)


def test_release_refuses_rake_layer_too(dbs, tmp_path):
    ours, yatri = dbs
    make_yatri(yatri).close()
    add_turnarounds(ours, yatri)
    platforms.add_to_db(ours, yatri)
    with sqlite3.connect(ours) as db:
        db.execute("DROP TABLE platform")
    with pytest.raises(LocalOnlyData, match="rake_next"):
        make_release(ours, tmp_path / "rel", tag="public")
