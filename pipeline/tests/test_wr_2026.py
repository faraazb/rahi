"""Golden tests against the WR PTT-79, w.e.f. 01.09.2026.

Each expectation was checked against a rendered page of the official PDF.
This edition changed the layout in ways the 2024 sheets did not exercise:
a Dahanu page holding two tables, AC sheets labelled under the numbers,
Central Railway Harbour trains with off-line CSMT/Panvel times, and
single-train last pages.
"""


import pytest

from mumbailocal.model import Diagnostics
from mumbailocal.paths import RAW_DIR
from mumbailocal.sources import wr

FIXTURE = RAW_DIR / "wr" / "2026-09-01"


@pytest.fixture(scope="module")
def parsed():
    if not FIXTURE.exists():
        pytest.skip("WR 2026 fixture PDFs not present")
    diag = Diagnostics()
    return wr.parse_dir(FIXTURE, diag), diag


@pytest.fixture(scope="module")
def trains(parsed):
    return parsed[0]


def find(trains, number, direction, variant=0):
    return next(t for t in trains if t.number == number and t.direction == direction and t.variant == variant)


def hm(minutes):
    m = minutes % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def at(t, code):
    return hm(next(s.time_min for s in t.stops if s.station_code == code))


def test_counts(trains):
    assert len(trains) == 1406
    assert sum(len(t.stops) for t in trains) == 21508


def test_no_structural_diagnostics(parsed):
    kinds = parsed[1].counts()
    for bad in ("direction-unknown", "page-without-grid", "station-unknown",
                "times-not-monotonic", "header-token-unknown"):
        assert bad not in kinds, kinds


def test_dahanu_page_holds_up_table_below_down_table(trains):
    t = find(trains, "93002", "UP")  # lower table: DRD 04:35 ... CCG 07:05
    assert t.origin == "DRD" and t.destination == "CCG"
    assert at(t, "DRD") == "04:35" and at(t, "CCG") == "07:05"
    dn = find(trains, "93041", "DN")  # upper table: CCG 20:20 ... DRD 23:05
    assert at(dn, "CCG") == "20:20" and at(dn, "DRD") == "23:05"


def test_dahanu_header_wins_only_when_consistent(trains):
    t = find(trains, "93033", "DN")  # header VR-DRD, but timed from Dadar 17:22
    assert t.origin == "DDR" and at(t, "DDR") == "17:22"


def test_ac_up_sheet_label_below_numbers(trains):
    t = find(trains, "94008", "UP")  # "*NON AC / SA & SU" in red
    assert t.is_ac and t.ac_weekdays_only and at(t, "BVI") == "05:20"


def test_harbour_train_from_csmt(trains):
    t = find(trains, "98701", "DN")  # C.R.GMN, "EX CSMT 04:28" in the Prabhadevi row
    assert t.operator == "CR" and t.origin == "CSMT" and t.destination == "GMN"
    assert [(s.station_code, hm(s.time_min)) for s in t.external_stops] == [("CSMT", "04:28")]
    assert "PBHD" not in {s.station_code for s in t.stops}
    assert t.stops[0].station_code == "MM" and at(t, "GMN") == "05:22"


def test_harbour_train_to_csmt(trains):
    t = find(trains, "98704", "UP")  # C.R.CSMT, "CSTM Arr 06:00" in the Mumbai Central row
    assert t.origin == "GMN" and t.destination == "CSMT"
    assert [(s.station_code, hm(s.time_min)) for s in t.external_stops] == [("CSMT", "06:00")]
    assert "BCL" not in {s.station_code for s in t.stops}


def test_link_label_column(trains):
    t = find(trains, "91393", "DN")  # header "WGN 1", EX CSMT 12:36 to Goregaon
    assert t.origin == "CSMT" and t.destination == "GMN" and "header WGN 1" in t.notes
    assert t.service.days == "1111110" and t.service.not_on_holidays


def test_single_train_last_pages(trains):
    dn = find(trains, "91055", "DN")
    assert dn.destination == "BVI" and at(dn, "CCG") == "01:00"
    up = find(trains, "91026", "UP")
    assert up.origin == "VR" and at(up, "VR") == "00:05"


def test_twelve_hour_typo_corrected(parsed):
    trains, diag = parsed
    t = find(trains, "91039", "DN")  # Prabhadevi printed "12:28" between 00:25 and 00:30
    assert at(t, "PBHD") == "00:28"
    assert any(i.kind == "time-corrected-12h" and i.where.startswith("91039") for i in diag.issues)


def test_semicolon_time(trains):
    assert at(find(trains, "94123", "DN"), "VLP") == "20:02"  # printed "20;02"


def test_starred_pass_cells(trains):
    t = find(trains, "92115", "DN")  # "P*" at Bandra and Borivali
    assert {p.split("@")[1] for p in t.pass_marks} == {"BA", "BVI"}
    assert not t.unrecognized_notes


def test_typo_station_labels(trains):
    t = find(trains, "93002", "UP")  # "CHERNI ROAD", "MERINE LINE"
    assert at(t, "CYR") == "06:55" and at(t, "MEL") == "06:58"


def test_ambiguous_day_note_is_flagged_not_guessed(trains):
    t = find(trains, "90047", "DN")  # prints "SUN & HOLIDAY" with no NOT/ONLY
    assert t.service.days == "1111111"
    assert any(n.startswith("ambiguous day note") for n in t.unrecognized_notes)
