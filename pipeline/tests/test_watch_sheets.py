"""The watcher saves each website PDF under the sheet name the parsers expect
(watch/sources.json "sheets" rules). Every PDF currently listed on the WR and CR
pages (watch/state/*.json) must land where the parsers look for it."""

import importlib.util
import json
from pathlib import Path

import pytest

from mumbailocal.sources import cr

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("watch", ROOT / "watch" / "watch.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
SOURCES = json.loads((ROOT / "watch" / "sources.json").read_text())


def live(railway):
    state = json.loads((ROOT / "watch" / "state" / f"{railway}.json").read_text())
    return [("page", {"key": k, "name": e["name"], "entry": e})
            for pg in state["pages"].values() for k, e in pg["files"].items()]


def saved(railway):
    current = live(railway)
    paths, unclassified, conflicts = watch.sheet_names(SOURCES[railway]["sheets"], current)
    assert unclassified == [] and conflicts == []
    return {c["name"].split("-", 1)[1]: paths[c["key"]] for _, c in current}


def test_wr_pdfs_land_on_the_wr_sheet_names():
    assert saved("wr") == {
        "DN TRAINS PTT 79 W.E.F. 01.09.2026.pdf": "dn.pdf",
        "UP TRAINS PTT 79 W.E.F. 01.09.2026.pdf": "up.pdf",
        "DN AC TRAINS PTT 79 W.E.F. 01.09.2026.pdf": "ac_dn.pdf",
        "UP AC TRAINS PTT 79 W.E.F. 01.09.2026.pdf": "ac_up.pdf",
        "DAHANU ROAD SERVICES PTT W.E.F. 01.09.2026.pdf": "drd.pdf",
        # Old Harbour sheets still linked from the WR page: kept, but not parsed.
        "UP HARBOUR  W.E.F. 22.11.2021.pdf": "other/1637561529471-UP HARBOUR  W.E.F. 22.11.2021.pdf",
        "HARBOUR SERVICES W.E.F   01.10.2022.pdf": "other/1680671789509-HARBOUR SERVICES W.E.F   01.10.2022.pdf",
    }


def test_cr_pdfs_land_on_every_cr_sheet():
    got = saved("cr")
    assert set(got.values()) - {p for p in got.values() if p.startswith("other/")} == set(cr.SHEETS) | {"holidays.pdf"}
    assert got["SUB PTT DN ML'24.pdf"] == "main_dn.pdf"
    assert got["HB AC PTT WEF 01.05.2026 (1).pdf"] == "hb_ac.pdf"
    assert got["THB PTT wef   13.01.2024.pdf"] == "thb.pdf"
    assert got["Suburban AC Services wef 16.04.2025.pdf"] == "ac.pdf"
    assert got["ABBREVIATIONS.pdf"].startswith("other/")


@pytest.mark.parametrize("name, sheet", [
    ("1800000000000-DN TRAINS PTT 80 W.E.F. 01.01.2027.pdf", "dn.pdf"),
    ("1800000000001-UP AC TRAINS PTT 80 W.E.F. 01.01.2027.pdf", "ac_up.pdf"),
])
def test_next_wr_edition(name, sheet):
    current = [("p", {"key": name, "name": name, "entry": {}})]
    assert watch.sheet_names(SOURCES["wr"]["sheets"], current)[0][name] == sheet


def test_unknown_pdf_and_duplicate_sheet_are_flagged():
    current = [("p", {"key": "a", "name": "1-DN TRAINS PTT 79.pdf", "entry": {"last_modified": "Mon, 01 Sep 2026 00:00:00 GMT"}}),
               ("p", {"key": "b", "name": "2-DN TRAINS PTT 80.pdf", "entry": {"last_modified": "Tue, 01 Dec 2026 00:00:00 GMT"}}),
               ("p", {"key": "c", "name": "3-NOTICE.pdf", "entry": {}})]
    paths, unclassified, conflicts = watch.sheet_names(SOURCES["wr"]["sheets"], current)
    assert paths == {"b": "dn.pdf", "a": "other/1-DN TRAINS PTT 79.pdf", "c": "other/3-NOTICE.pdf"}
    assert unclassified == ["3-NOTICE.pdf"] and len(conflicts) == 1
