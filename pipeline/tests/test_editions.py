"""w.e.f. dates from the railways' PDF names, per line."""

import json

import pytest

from mumbailocal import editions
from mumbailocal.cli import _cr_editions, _ntes_editions, _wr_editions
from mumbailocal.paths import RAW_DIR


@pytest.mark.parametrize("name, expected", [
    ("1788159627721-DN TRAINS PTT 79 W.E.F. 01.09.2026.pdf", "2026-09-01"),
    ("1777550323377-DN HB REVISED PTT WEF 01.05.2026.pdf", "2026-05-01"),
    ("1777550442158-HB AC PTT WEF 01.05.2026 (1).pdf", "2026-05-01"),
    ("1786691264142-PTT OF 15 CAR TT ON MAINLINE WEF 15 AUG 26.pdf", "2026-08-15"),
    ("1781174782507-THB PTT wef   13.01.2024.pdf", "2024-01-13"),
    ("1770378640224-Suburban AC Services wef 16.04.2025.pdf", "2025-04-16"),
    ("DAHANU ROAD SERVICES PTT W.E.F. 01.09.2026.pdf", "2026-09-01"),
    ("1728294831372-SUB PTT DN ML'24.pdf", None),
    ("1781160194413-PTT LNL-PUNE.pdf", None),
    ("PTT WEF 31.02.2026.pdf", None),  # not a date
])
def test_wef_from_file_name(name, expected):
    assert editions.wef(name) == expected


def test_wr_folder_without_sources_is_named_by_its_wef(tmp_path):
    d = tmp_path / "2026-09-01"
    d.mkdir()
    (d / "dn.pdf").write_bytes(b"")
    assert editions.line_editions(d, lambda n: "WR") == {
        "WR": {"effective_from": "2026-09-01", "as_of": "2026-09-01", "files": ["dn.pdf"]}}


def test_watcher_snapshot_uses_original_names_not_folder_date(tmp_path):
    d = tmp_path / "2026-08-30"  # watcher folders are named by Last-Modified, not w.e.f.
    d.mkdir()
    name = "1788159627721-DN TRAINS PTT 79 W.E.F. 01.09.2026.pdf"
    (d / name).write_bytes(b"")
    (d / "SOURCES.txt").write_text(
        "# file\tLast-Modified\tsha256\turl\n"
        f"{name}\tSun, 30 Aug 2026 10:00:00 GMT\tabc\thttps://oldwr.indianrailways.gov.in/cris//uploads/files/"
        "1788159627721-DN%20TRAINS%20PTT%2079%20W.E.F.%2001.09.2026.pdf\n")
    assert editions.line_editions(d, lambda n: "WR")["WR"] == {
        "effective_from": "2026-09-01", "as_of": "2026-08-30", "files": [name]}


def test_current_snapshots():
    wr_dir, cr_dir, ntes_dir = RAW_DIR / "wr" / "2026-09-01", RAW_DIR / "cr" / "2026-11-01", RAW_DIR / "ntes" / "2026-11-07"
    if not (wr_dir.exists() and cr_dir.exists() and ntes_dir.exists()):
        pytest.skip("snapshots not present")
    meta = _wr_editions(wr_dir) | _cr_editions(cr_dir) | _ntes_editions(ntes_dir)
    assert meta["wr_effective_from"] == "2026-09-01"
    assert meta["cr_effective_from"] == "2026-08-15"  # 15-car sheet, the newest CR main line change
    assert meta["hr_effective_from"] == "2026-05-01"
    assert meta["thr_effective_from"] == "2024-01-13"
    assert meta["ur_effective_from"] == "2025-12-15"
    assert meta["pune_effective_from"] == ""  # Pune sheets print no w.e.f.
    assert meta["pune_as_of"] == "2026-11-01"
    assert meta["dvp_effective_from"] == "" and meta["dvp_as_of"] == "2026-11-07"
    assert meta["nm_as_of"] == "2026-11-07"
    assert json.loads(meta["hr_files"]) == ["hb_ac.pdf", "hb_dn.pdf", "hb_up.pdf"]
    assert "holidays.pdf" not in meta["cr_files"]
