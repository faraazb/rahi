"""Golden tests against the CR sheets downloaded 2026-11-01 (data/raw/cr/2026-11-01).

Each expectation was checked against a rendered page of the official PDF.
The CR sheets differ from WR's: branches stacked in the rows (Kalyan ->
Karjat and -> Kasara), passes printed "…", link codes in the header,
Panvel <-> Goregaon trains split across the DN and UP tables at Vadala,
white placeholder zeros, and arrival/departure rows on the Pune sheets.
"""

import pytest

from mumbailocal.model import NOT_SUNDAY, Diagnostics
from mumbailocal.paths import RAW_DIR
from mumbailocal.sources import cr
from mumbailocal.stations import StationTable

FIXTURE = RAW_DIR / "cr" / "2026-11-01"


@pytest.fixture(scope="module")
def parsed():
    if not FIXTURE.exists():
        pytest.skip("CR 2026 fixture PDFs not present")
    diag = Diagnostics()
    return cr.parse_dir(FIXTURE, diag), diag


@pytest.fixture(scope="module")
def by_line(parsed):
    return parsed[0]


def find(by_line, line, number, direction=None):
    return next(t for t in by_line[line] if t.number == number and direction in (None, t.direction))


def hm(minutes):
    m = minutes % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def stops(t):
    return [(s.station_code, hm(s.time_min)) for s in t.stops]


def test_trip_counts(by_line):
    # Yatri's snapshot has the same numbers of trains on every line.
    assert {line: len(ts) for line, ts in by_line.items()} == {
        "CR": 895, "HR": 614, "THR": 262, "UR": 50, "PUNE": 42}


def test_no_blocking_diagnostics(parsed):
    from mumbailocal import quality
    by_line, diag = parsed
    verdict = quality.check([t for ts in by_line.values() for t in ts], diag)
    assert verdict.ok, str(verdict)


def test_kasara_branch_follows_kalyan(by_line):
    # main_dn p18: 96649 TL 61, no time printed at Diva (blank cell, seen).
    t = find(by_line, "CR", "96649", "DN")
    codes = [c for c, _ in stops(t)]
    assert codes[:2] == ["CSMT", "MSD"] and codes[-4:] == ["KYN", "SHAD", "ABY", "TLA"]
    assert "DIVA" not in codes and codes[codes.index("MBQ") + 1] == "KOPR"
    assert (t.origin, t.destination) == ("CSMT", "TLA")
    assert hm(t.stops[-1].time_min) == "00:33" and t.stops[-1].time_min >= 1440
    assert t.is_fast  # skips Diva


def test_karjat_branch_small_hours(by_line):
    # main_dn p1: 96101 S 1, CSMT 00:12 ... Kalyan 01:40, Vithalwadi 1:44 ... Karjat 2:33.
    t = find(by_line, "CR", "96101", "DN")
    assert stops(t)[0] == ("CSMT", "00:12")
    assert ("KYN", "01:40") in stops(t) and stops(t)[-1] == ("KJT", "02:33")
    assert "SHAD" not in dict(stops(t))
    assert not t.is_fast


def test_day_and_ac_marks(by_line):
    # main_dn p1: X under 97003 and 97005 only; 95701 "K 3 / AC".
    assert find(by_line, "CR", "97003", "DN").service.days == NOT_SUNDAY
    assert find(by_line, "CR", "97003", "DN").service.not_on_holidays
    assert find(by_line, "CR", "97001", "DN").service.days == "1111111"
    t = find(by_line, "CR", "95701", "DN")
    assert t.is_ac and not t.ac_weekdays_only
    assert stops(t)[0] == ("CSMT", "05:20") and ("TNA", "06:01") in stops(t) and stops(t)[-1] == ("KYN", "06:24")
    # ac p1: 95209 "BL 9 / AC#": non-AC on weekends and holidays.
    assert find(by_line, "CR", "95209", "DN").ac_weekdays_only


def test_white_placeholder_zeros_ignored(by_line):
    # ac p4: an invisible "00:00" sits in the Kasara row of 95210's column.
    t = find(by_line, "CR", "95210", "UP")
    assert stops(t)[0] == ("BUD", "10:42") and stops(t)[-1] == ("CSMT", "12:12")


def test_fifteen_car_sheet_wins(by_line):
    # main_15car p1: 95003 "DKP 1 / 15 C", "DR" in the CSMT cell, Dadar 07:43 .. Khopoli 9:51.
    t = find(by_line, "CR", "95003", "DN")
    assert t.cars == 15 and t.sources[0].startswith("main_15car.pdf")
    assert stops(t)[0] == ("DR", "07:43") and stops(t)[-1] == ("KHPI", "09:51")


def test_harbour_rake_note_is_not_a_stop(by_line):
    # hb_ac p1: 98009 "R/O / VVD 2 / 04:56" above its first time, Vadala 05:06.
    t = find(by_line, "HR", "98009", "DN")
    assert stops(t)[0] == ("VDLR", "05:06") and stops(t)[-1] == ("PNVL", "06:08")
    assert any(n.startswith("rake of VVD 2") for n in t.notes)
    assert t.is_ac and t.service.days == NOT_SUNDAY


def test_harbour_off_line_terminal(by_line):
    # hb_dn p16: 91491 "WBO 1", Goregaon 21:38, then "BVI" (Kurla row) "21:50" (Tilaknagar row).
    t = find(by_line, "HR", "91491", "DN")
    assert stops(t)[-1] == ("GMN", "21:38")
    assert [(s.station_code, hm(s.time_min)) for s in t.external_stops] == [("BVI", "21:50")]
    assert t.destination == "BVI"


def test_panvel_goregaon_joined_at_vadala(by_line):
    # hb_up p3 PNVL 05:57 .. Vadala 06:58, hb_dn p2 Vadala 07:02 .. Goregaon 07:39 (PLGN 1).
    t = find(by_line, "HR", "98901")
    assert t.direction == "DN"  # odd number
    assert stops(t)[0] == ("PNVL", "05:57") and stops(t)[-1] == ("GMN", "07:39")
    assert ("VDLR", "07:02") in stops(t) and ("GTBN", "06:52") in stops(t) and ("KCE", "07:07") in stops(t)
    assert sum(1 for x in by_line["HR"] if x.number == "98901") == 1


def test_unexplained_hash_is_not_ac(by_line):
    # hb_dn p13: 98193 "PL 155 / L/SPL / #"; only "AC#" has a legend.
    t = find(by_line, "HR", "98193", "DN")
    assert t.ladies_special and not t.is_ac
    assert any("#" in n for n in t.unrecognized_notes)


def test_trans_harbour_branches(by_line):
    # thb p1: 99001 TPL 1 TNA 00:05 .. TUH 00:26, JNJ 00:30 .. PNVL 00:57;
    # 99401 TV 1 TNA 05:25 .. TUH 05:46, SNPD 05:50, VSH 05:54.
    t = find(by_line, "THR", "99001", "DN")
    assert stops(t)[0] == ("TNA", "00:05") and stops(t)[-1] == ("PNVL", "00:57")
    assert ("JNJ", "00:30") in stops(t) and "SNCR" not in dict(stops(t))
    v = find(by_line, "THR", "99401", "DN")
    assert stops(v)[-3:] == [("TUH", "05:46"), ("SNCR", "05:50"), ("VSH", "05:54")]
    # The copy of 99003 printed on the Harbour sheet ("TNA" in its CSMT cell) is dropped.
    assert not any(x.number == "99003" for x in by_line["HR"])


def test_port_line_two_origins(by_line):
    # port p1: 99601 UNU 1 Nerul 06:15, Seawoods 06:19, Targhar 06:25 .. Uran 06:49;
    # 99701 UBR 1 Belapur 05:30, Targhar 05:39 .. Uran 06:03.
    t = find(by_line, "UR", "99601", "DN")
    assert stops(t)[:3] == [("NEU", "06:15"), ("SWDV", "06:19"), ("TRGR", "06:25")]
    assert stops(t)[-1] == ("URAN", "06:49")
    b = find(by_line, "UR", "99701", "DN")
    assert stops(b)[:2] == [("BEPR", "05:30"), ("TRGR", "05:39")] and stops(b)[-1] == ("URAN", "06:03")
    assert not t.is_fast and not b.is_fast


def test_pune_arrival_departure_rows(by_line):
    # lnl_pune p1: 99803 Lonavala 06.30 .. Khadki 07.31, Shivajinagar "07.55 / ...", Pune "X".
    t = find(by_line, "PUNE", "99803", "DN")
    assert stops(t)[0] == ("LNL", "06:30") and stops(t)[-1] == ("SVJR", "07:55")
    # 99901: "X" at Lonavala..Vadgaon, first time Talegaon 00.35, Pune Jn 01.37.
    s = find(by_line, "PUNE", "99901", "DN")
    assert stops(s)[0] == ("TGN", "00:35") and stops(s)[-1] == ("PUNE", "01:37")
    assert len(s.stops) == 12 and not s.is_fast


def test_station_graph():
    t = StationTable("CR")
    assert t.path("KYN", "KSRA")[:2] == ["KYN", "SHAD"]
    assert t.path("VLDI", "SHAD") == ["VLDI", "KYN", "SHAD"]
    assert t.by_code["SHAD"].seq == t.by_code["VLDI"].seq == t.by_code["KYN"].seq + 1
    u = StationTable("UR")
    assert u.path("BEPR", "URAN")[:2] == ["BEPR", "TRGR"] and u.path("NEU", "TRGR") == ["NEU", "SWDV", "TRGR"]
