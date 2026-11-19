"""Regression suite over every WR timetable release we hold (2017-2026).

WR changes the sheet layout from release to release. Each change the parser
learned to handle is pinned here, so a fix for one release cannot silently
break another. Three kinds of check:

* snapshot   trip count, stop count and the blocking diagnostics per release.
             Any parser change that moves these must be looked at. The
             blocking diagnostics left are source defects that were checked
             by eye (truncated train numbers, a missing label, merged-cell
             Dahanu sheets); they are listed in RELEASES below.
* spot       individual trains checked against rendered pages.
* agreement  consecutive releases share many unchanged trains; those must
             parse identically. A misread rarely repeats across PDFs made
             with different tools, so high agreement means the reads are right.

Unsupported sheets are excluded explicitly: 2022-06-20 ac.pdf (SWTT-76
working-timetable format, one combined DN/UP AC file).
"""

from collections import Counter

import pytest

from mumbailocal import quality
from mumbailocal.model import NOT_SUNDAY, Diagnostics
from mumbailocal.paths import RAW_DIR
from mumbailocal.sources import wr

RAW = RAW_DIR / "wr"

# release -> (excluded files, trips, stops, blocking diagnostics)
RELEASES = {
    "2026-09-01": ((), 1406, 21508, {}),
    "2024-10-12": ((), 96, 1333, {}),  # AC sheets only were archived
    "2024-01-04": ((), 1289, 20687, {"word-outside-columns": 1}),
    # dn p.28: two car counts printed in one cell
    "2023-04-05": ((), 1283, 20576, {"header-code-unknown": 1, "header-token-unknown": 1}),
    # Dahanu sheet: times float between rows inside tall merged cells
    "2022-06-20": (("ac.pdf",), 1270, 20150, {
        "station-unknown": 2, "time-without-station": 72, "times-not-monotonic": 1,
        "train-too-few-stops": 7, "word-outside-columns": 3}),
    "2021-11-22": ((), 1263, 20189, {"station-unknown": 1, "time-without-station": 2, "word-outside-columns": 3}),
    "2021-01-29": ((), 1197, 19056, {
        "page-without-grid": 1, "station-unknown": 1, "time-without-station": 2, "times-not-monotonic": 1}),
    # up p.3: five train numbers printed truncated ("4", "6", ...);
    # Dahanu sheets name MEMU/passenger terminals (Bharuch, Valsad)
    "2018-11-01": ((), 1251, 19865, {"column-without-number": 5, "header-token-unknown": 26, "times-not-monotonic": 1}),
    "2017-10-04": ((), 1246, 19542, {
        "column-without-number": 2, "header-token-unknown": 14, "page-without-grid": 3,
        "station-unknown": 1, "word-outside-columns": 1}),
}

_cache: dict[str, tuple[list, Diagnostics]] = {}


def parsed(release: str):
    if release not in _cache:
        if not (RAW / release).exists():
            pytest.skip(f"{release} PDFs not present")
        diag = Diagnostics()
        trains = wr.parse_dir(RAW / release, diag, frozenset(RELEASES[release][0]))
        _cache[release] = (trains, diag)
    return _cache[release]


def find(release, number, direction, variant=0):
    trains, _ = parsed(release)
    return next(t for t in trains if (t.number, t.direction, t.variant) == (number, direction, variant))


def hm(minutes):
    return f"{minutes % 1440 // 60:02d}:{minutes % 60:02d}"


def at(t, code):
    return hm(next(s.time_min for s in t.stops if s.station_code == code))


@pytest.mark.parametrize("release", RELEASES)
def test_snapshot(release):
    trains, diag = parsed(release)
    _, n_trips, n_stops, blocking = RELEASES[release]
    verdict = quality.check(trains, diag)
    assert (len(trains), sum(len(t.stops) for t in trains)) == (n_trips, n_stops)
    assert dict(verdict.blocking) == blocking


# -- spot checks against rendered pages -----------------------------------

def test_2017_station_column_in_middle_of_spread():
    t = find("2017-10-04", "90678", "UP")  # the one train printed left of STATIONS (p.25)
    assert at(t, "BVI") == "15:41" and at(t, "CCG") == "16:46"
    t = find("2017-10-04", "90680", "UP")
    assert t.origin == "BYR" and at(t, "BYR") == "15:29" and at(t, "ADH") == "16:06"


def test_2017_old_dahanu_sheet_keeps_only_suburban_trains():
    t = find("2017-10-04", "93005", "DN")  # header "CHURCHGATE / DAHANU", labels "CHURCHGAT", "DAHANU RD"
    assert (t.origin, t.destination) == ("CCG", "DRD")
    assert at(t, "CCG") == "04:58" and at(t, "DRD") == "07:30"
    trains, _ = parsed("2017-10-04")
    assert not any(t.number.startswith(("59", "69", "71")) for t in trains)  # MEMU / passenger / DMU


def test_2018_missing_label_inferred():
    t = find("2018-11-01", "90352", "UP")  # p.12 prints no "Ram Mandir" label
    assert at(t, "GMN") == "09:43" and at(t, "RMAR") == "09:45" and at(t, "JOS") == "09:48"


def test_2018_truncated_numbers_do_not_leak_times():
    _, diag = parsed("2018-11-01")
    assert sum(i.kind == "column-without-number" and i.where.startswith("up.pdf#3") for i in diag.issues) == 5
    t = find("2018-11-01", "92006", "UP")  # neighbour of the truncated columns
    assert t.stops and t.stops[0].station_code == "VR"


def test_2018_typo_vile_parle_still_read():
    # Every DN page labels the row "Ville Parle"; before loose matching the row
    # was dropped and no train stopped there (2024, spelt right: 301).
    trains, _ = parsed("2018-11-01")
    assert sum(t.direction == "DN" and any(s.station_code == "VLP" for s in t.stops) for t in trains) == 289


def test_2021_booklet_up_sheet_direction_from_station_order():
    t = find("2021-01-29", "90034", "UP")  # label only in page title "VIRAR- CHURCHGATE ( UP )"
    assert t.origin == "BVI" and at(t, "BVI") == "04:50" and at(t, "ADH") == "05:11"
    t = find("2021-01-29", "92002", "UP")
    assert [(s.station_code, hm(s.time_min)) for s in t.stops][:5] == [
        ("VR", "04:13"), ("BSR", "04:22"), ("BYR", "04:30"), ("BVI", "04:39"), ("ADH", "04:51")]


def test_2021_special_train_number():
    t = find("2021-11-22", "SPL-2", "UP")  # column headed "DRD / SPL-2"
    assert t.origin == "DRD" and at(t, "ADH") == "06:30"


def test_2021_not_on_sunday():
    t = find("2021-11-22", "90098", "UP")
    assert t.service.days == NOT_SUNDAY and at(t, "GMN") == "06:21"


def test_2021_dahanu_arrival_departure_rows():
    t = find("2021-11-22", "93005", "DN")  # "CHURCHGATE D", "DADAR A"/"D" rows
    assert [(s.station_code, hm(s.time_min)) for s in t.stops if s.station_code in ("CCG", "DDR", "BA", "ADH", "BVI", "DRD")] == [
        ("CCG", "04:58"), ("DDR", "05:15"), ("BA", "05:22"), ("ADH", "05:31"), ("BVI", "05:47"), ("DRD", "07:30")]


def test_2023_dahanu_sheet_without_direction_label():
    t = find("2023-04-05", "93031", "DN")  # header: cars / number / DDR / DRD, no "DN"
    assert t.origin == "DDR" and at(t, "DDR") == "18:00" and at(t, "BA") == "18:06"


# -- agreement between consecutive releases --------------------------------

@pytest.mark.parametrize("newer,older,minimum", [
    ("2024-01-04", "2023-04-05", 0.97),
    ("2022-06-20", "2021-11-22", 0.95),
    ("2021-11-22", "2021-01-29", 0.95),
])
def test_unchanged_trains_parse_identically(newer, older, minimum):
    a = {(t.number, t.direction, t.variant): t for t in parsed(newer)[0]}
    b = {(t.number, t.direction, t.variant): t for t in parsed(older)[0]}
    sig = lambda t: [(s.station_code, s.time_min) for s in t.stops]  # noqa: E731
    common = a.keys() & b.keys()
    assert sum(sig(a[k]) == sig(b[k]) for k in common) / len(common) >= minimum


# -- release gate -----------------------------------------------------------

def test_gate_passes_current_release():
    trains, diag = parsed("2026-09-01")
    assert quality.check(trains, diag, parsed("2024-01-04")[0]).ok


def test_gate_holds_unsupported_sheet():
    diag = Diagnostics()
    trains = wr.parse_dir(RAW / "2022-06-20", diag)  # including the SWTT-76 AC sheet
    verdict = quality.check(trains, diag)
    without = sum(RELEASES["2022-06-20"][3].values())
    assert not verdict.ok and sum(verdict.blocking.values()) > without + 50
    assert verdict.blocking["header-code-unknown"] > 0  # its link codes CD, CP, BJ


def test_gate_holds_large_trip_swing():
    trains, diag = parsed("2024-10-12")  # AC sheets only: 96 trips after 1289
    verdict = quality.check(trains, Diagnostics(), parsed("2024-01-04")[0])
    assert not verdict.ok and "trip count" in verdict.notes[0]
