"""Which edition of the timetable each line comes from.

Railways print the date a timetable takes effect ("w.e.f.", with effect from)
in the PDF's file name on their website, not in a form the parser can rely on
inside the PDF:

    DN TRAINS PTT 79 W.E.F. 01.09.2026.pdf
    DN HB REVISED PTT WEF 01.05.2026.pdf
    PTT OF 15 CAR TT ON MAINLINE WEF 15 AUG 26.pdf
    THB PTT wef   13.01.2024.pdf

A snapshot folder's SOURCES.txt lists each saved file with the URL it came
from (last tab-separated column), so the original name survives renaming.
A line's effective date is the newest w.e.f. among its files: the last time
any part of its timetable changed. Folders without SOURCES.txt are the
hand-made WR releases under data/raw/wr/<w.e.f. date>/, named by that date.

`as_of` is the snapshot folder's date (when the files were taken), which is
all the NTES lines have.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date
from pathlib import Path
from typing import Callable

MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
WEF = re.compile(
    r"w\s*\.?\s*e\s*\.?\s*f\s*\.?\s*(\d{1,2})[\s./-]+(\d{1,2}|[a-z]{3})[a-z]*[\s./-]+(\d{4}|\d{2})(?!\d)",
    re.IGNORECASE)
DATED = re.compile(r"\d{4}-\d{2}-\d{2}")


def wef(name: str) -> str | None:
    """The w.e.f. date printed in a file name, as YYYY-MM-DD."""
    m = WEF.search(name)
    if not m:
        return None
    day, month, year = m.groups()
    month_n = int(month) if month.isdigit() else MONTHS.get(month[:3].lower())
    year_n = int(year) + (2000 if len(year) == 2 else 0)
    try:
        return date(year_n, month_n or 0, int(day)).isoformat()
    except ValueError:
        return None


def original_names(folder: Path) -> dict[str, str]:
    """Saved file name -> its name on the website, from SOURCES.txt."""
    sources = folder / "SOURCES.txt"
    if not sources.exists():
        return {}
    out = {}
    for line in sources.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 2:
            out[cols[0]] = urllib.parse.unquote(cols[-1].rsplit("/", 1)[-1])
    return out


def line_editions(folder: Path, line_of_file: Callable[[str], str | None],
                  pattern: str = "*.pdf") -> dict[str, dict]:
    """{line: {"effective_from", "as_of", "files"}} for the lines with files in folder."""
    names = original_names(folder)
    as_of = folder.name if DATED.fullmatch(folder.name) else None
    dates: dict[str, list[str]] = {}
    files: dict[str, list[str]] = {}
    for p in sorted(folder.glob(pattern)):
        line = line_of_file(p.name)
        if not line:
            continue
        files.setdefault(line, []).append(p.name)
        d = wef(names.get(p.name, p.name))
        dates.setdefault(line, [])
        if d:
            dates[line].append(d)
    out = {}
    for line, ds in dates.items():
        effective = max(ds) if ds else None
        if effective is None and not names and as_of:
            effective = as_of  # hand-made folder named by its w.e.f. date
        out[line] = {"effective_from": effective, "as_of": as_of, "files": files[line]}
    return out


def meta(editions: dict[str, dict]) -> dict[str, str]:
    """Database meta rows: <line>_effective_from and <line>_as_of ("" when unknown), and
    <line>_files (JSON list of the line's source files)."""
    out = {}
    for line, e in editions.items():
        k = line.lower()
        out |= {f"{k}_effective_from": e["effective_from"] or "", f"{k}_as_of": e["as_of"] or "",
                f"{k}_files": json.dumps(e["files"])}
    return out
