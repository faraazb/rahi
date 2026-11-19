"""Golden tests against the archived WR PTT of 04.01.2024.

Each expectation was checked by eye against a rendered page of the official
PDF, so a failure means the parser changed behaviour, not that the data did.
"""


import pytest

from mumbailocal.model import NOT_SUNDAY, Diagnostics
from mumbailocal.paths import RAW_DIR
from mumbailocal.sources import wr

FIXTURE = RAW_DIR / "wr" / "2024-01-04"


@pytest.fixture(scope="module")
def trains():
    if not FIXTURE.exists():
        pytest.skip("WR 2024 fixture PDFs not present")
    return wr.parse_dir(FIXTURE, Diagnostics())


def find(trains, number, direction, variant=0):
    return next(t for t in trains if t.number == number and t.direction == direction and t.variant == variant)


def hm(t, code):
    m = next(s.time_min for s in t.stops if s.station_code == code) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def test_counts(trains):
    assert len(trains) == 1289
    assert sum(len(t.stops) for t in trains) == 20687


def test_first_down_train_starts_mid_list(trains):
    t = find(trains, "90001", "DN")  # page 1: BVI-bound, starts at Bandra 04:05
    assert t.stops[0].station_code == "BA" and hm(t, "BA") == "04:05"
    assert t.destination == "BVI" and t.cars == 12 and not t.is_ac


def test_not_on_sunday_note(trains):
    t = find(trains, "92003", "DN")  # "NOT ON SUN ONLY" printed in its column
    assert t.service.days == NOT_SUNDAY and t.cars == 15


def test_ac_and_weekend_non_ac(trains):
    t = find(trains, "94083", "DN", variant=1)  # 08:46 CCG, "ON SAT & SUN NON AC"
    assert hm(t, "CCG") == "08:46" and t.is_ac and t.ac_weekdays_only
    assert t.destination == "BVI" and t.is_fast


def test_number_reused_for_a_different_trip(trains):
    first = find(trains, "94083", "DN", variant=0)  # 06:35 CCG to Virar
    assert hm(first, "CCG") == "06:35" and first.destination == "VR"


def test_pass_marks_are_not_stops(trains):
    t = find(trains, "90415A", "DN")  # "P" printed at two stations
    assert sum(p.startswith("pass@") for p in t.pass_marks) == 2


def test_blank_terminal_keeps_header_destination(trains):
    t = find(trains, "90305", "DN")  # Borivali cell blank, header says BVI
    assert t.stops[-1].station_code == "KILE" and hm(t, "KILE") == "11:09"
    assert t.destination == "BVI" and t.terminal_without_time == "BVI"


def test_dahanu_train_merged_across_sheets(trains):
    t = find(trains, "93005", "DN")
    assert t.stops[0].station_code == "CCG" and t.stops[-1].station_code == "DRD"
    assert {s.split("#")[0] for s in t.sources} == {"dn.pdf", "drd.pdf"}


def test_up_header_code_is_origin(trains):
    t = find(trains, "90002", "UP")
    assert t.origin == "ADH" and t.destination == "CCG"


def test_legend_hash_means_not_on_sunday_on_that_page(trains):
    t = find(trains, "91027", "DN")  # header NSP#, page legend "# NOT ON SUNDAY"
    assert t.service.days == NOT_SUNDAY


def test_legend_hash_means_non_ac_weekend_on_up_sheet(trains):
    t = find(trains, "94018", "UP")  # header VR#, legend "# Non AC on SATURDAY & SUNDAY"
    assert t.is_ac and t.ac_weekdays_only


def test_legend_star_passing_named_station(trains):
    t = find(trains, "92042", "UP")  # VR*, legend "* Passing(Will not halt at BVI)"
    assert "BVI" not in {s.station_code for s in t.stops}


def test_footer_text_does_not_leak_into_columns(trains):
    assert sum(t.ladies_special for t in trains) == 11
    assert not any("Passing" in n for t in trains for n in t.unrecognized_notes)
