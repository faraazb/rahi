"""Golden tests against the NTES schedule pages saved 2026-11-07 (data/raw/ntes/2026-11-07).

Each expectation was read off the saved page (Arr / Dep columns).
"""

import sqlite3

import pytest

from mumbailocal import build_db, quality
from mumbailocal.model import Diagnostics
from mumbailocal.paths import RAW_DIR
from mumbailocal.sources import ntes
from mumbailocal.stations import StationTable

FIXTURE = RAW_DIR / "ntes" / "2026-11-07"


@pytest.fixture(scope="module")
def parsed():
    if not FIXTURE.exists():
        pytest.skip("NTES 2026-11-07 snapshot not present")
    diag = Diagnostics()
    return ntes.parse_dir(FIXTURE, diag), diag


@pytest.fixture(scope="module")
def by_line(parsed):
    return parsed[0]


def find(by_line, line, number):
    return next(t for t in by_line[line] if t.number == number)


def hm(m):
    return None if m is None else f"{m % 1440 // 60:02d}:{m % 60:02d}"


def stops(t):
    return [(s.station_code, hm(s.time_min)) for s in t.stops]


def test_counts_and_gate(parsed):
    by_line, diag = parsed
    assert {k: len(v) for k, v in by_line.items()} == {"DVP": 31, "NM": 16}
    assert quality.check([t for ts in by_line.values() for t in ts], diag).ok
    # Only the three Panvel -> Vasai/Dahanu MEMUs that run through Kopar without halting.
    assert sorted(i.where for i in diag.issues) == ["69161 DVP", "69165 DVP", "69167 DVP"]


def test_days_of_run():
    assert ntes.days_of_run("Daily") == "1111111"
    assert ntes.days_of_run("Mon,Tue,Wed,Thu,Fri") == "1111100"
    assert ntes.days_of_run("Sometimes") is None


def test_arrival_kept_apart_from_departure(by_line):
    # 61002 DI-BOR: Vasai Road arr 06:45 dep 07:00; Boisar arr 08:20 (destination).
    t = find(by_line, "DVP", "61002")
    vasai = next(s for s in t.stops if s.station_code == "BSR")
    assert (hm(vasai.arr_min), hm(vasai.time_min)) == ("06:45", "07:00")
    assert stops(t)[0] == ("DI", "05:49") and stops(t)[-1] == ("BOR", "08:20")
    assert t.stops[-1].arr_min is None
    assert t.direction == "UP" and (t.origin, t.destination) == ("DI", "BOR")


def test_kopar_upper_level_is_kopar(by_line):
    # NTES codes Kopar's upper level KORU; it is the Kopar interchange.
    t = find(by_line, "DVP", "61003")
    assert [c for c, _ in stops(t)] == ["BSR", "JCNR", "KARD", "KHBV", "BIRD", "KOPR", "DIVA"]
    assert t.direction == "DN" and not t.is_fast


def test_panvel_vasai_misses_diva(by_line):
    # 69166 BSR-PNVL: ... Kopar 17:27, Dativali 17:35 ... Panvel 18:25, no Diva.
    t = find(by_line, "DVP", "69166")
    codes = [c for c, _ in stops(t)]
    assert "DIVA" not in codes and codes[codes.index("KOPR") + 1] == "DTVL"
    assert not t.is_fast
    # 69165 PNVL-BSR runs Dativali -> Bhiwandi Road without halting at Kopar.
    assert find(by_line, "DVP", "69165").is_fast


def test_weekday_memu(by_line):
    t = find(by_line, "DVP", "61017")
    assert t.service.days == "1111100" and not t.service.not_on_holidays
    assert stops(t) == [("DIVA", "09:10"), ("DTVL", "09:14"), ("NIIJ", "09:21"), ("TPND", "09:30"),
                        ("NVRD", "09:35"), ("KLMG", "09:39"), ("PNVL", "09:50")]


def test_matheran(by_line):
    # 52103 NRLN-MAE: Neral 08:50, Jumma Patti 09:36, Water Pipe 10:22, Aman Lodge 11:12, Matheran 11:30.
    t = find(by_line, "NM", "52103")
    assert stops(t) == [("NRL", "08:50"), ("JTT", "09:36"), ("WTP", "10:22"), ("ANLG", "11:12"), ("MAE", "11:30")]
    assert t.direction == "DN"
    assert find(by_line, "NM", "52154").stops[-1].station_code == "ANLG"


def test_route_positions_on_a_loop(by_line, tmp_path):
    # Panvel -> Vasai is 11 stations along the track; 69165 halts at 10 of them.
    db_path = tmp_path / "t.sqlite"
    build_db.build(db_path, by_line, {})
    db = sqlite3.connect(db_path)
    seq, pos = db.execute(
        "SELECT MAX(st.seq), MAX(st.pos) FROM stop_time st JOIN train t ON t.id = st.train_id "
        "WHERE t.number = '69165'").fetchone()
    assert (seq, pos) == (10, 11)
    # Station lists keep the CSV order: the Vasai trunk to Dahanu Road, then each branch.
    order = [c for (c,) in db.execute(
        "SELECT s.code FROM line_station ls JOIN station s ON s.id = ls.station_id "
        "JOIN line l ON l.id = ls.line_id WHERE l.code = 'DVP' ORDER BY ls.ord")]
    assert order[16:19] == ["DRD", "DI", "DTVL"] and order[-1] == "ROHA"
    assert StationTable("DVP").path("PNVL", "BSR")[5:7] == ["DTVL", "KOPR"]
