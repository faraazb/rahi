"""Generic coordinate-based extraction for timetable PDFs laid out as a
station x train matrix: columns are trains, rows are stations, a cell holds a
time, and a blank cell means the train does not stop there.

This module knows nothing about any particular railway. A source adapter
supplies the anchor pattern (how to recognise the train-number header row)
and interprets the header tokens, row labels and cell contents it returns.

Why coordinates and not text layout: blanks are meaningful (skip = fast
train), and notes such as "NOT ON SUN" are written vertically inside a
column. Only x/y positions keep each word attached to the right train.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from statistics import median


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    top: float
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Column:
    index: int
    cx: float
    left: float
    right: float
    # One entry per header line, each a list of words in x order.
    header: list[list[Word]] = field(default_factory=list)

    def header_texts(self) -> list[str]:
        return [" ".join(w.text for w in ws) for ws in self.header if ws]


@dataclass
class Row:
    label: str
    top: float
    cells: dict[int, list[Word]]  # column index -> words in x order


@dataclass
class Grid:
    page_number: int
    columns: list[Column]
    rows: list[Row]
    # Label-area text of the header band plus any title lines above it.
    header_label: str
    label_right: float
    pitch: float
    unassigned: list[Word]
    # The station-name column normally sits left of every train column, but a
    # booklet spread can put it in the middle (WR 2017 p.25).
    label_left: float = float("-inf")

    def is_label(self, w: Word) -> bool:
        return self.label_left <= w.cx < self.label_right


def _is_white(color) -> bool:
    return isinstance(color, (tuple, list)) and len(color) in (1, 3) and all(
        isinstance(c, (int, float)) and c >= 0.95 for c in color)


def page_words(page, x_tolerance: float = 1.5, y_tolerance: float = 2.0,
               drop_white: bool = False) -> list[Word]:
    """Words on a page. drop_white skips white-filled text: some sheets put
    invisible placeholders ("00:00", "0") in empty cells (CR 2024-26)."""
    words = page.extract_words(
        x_tolerance=x_tolerance,
        y_tolerance=y_tolerance,
        keep_blank_chars=False,
        use_text_flow=False,
        extra_attrs=["non_stroking_color"] if drop_white else None,
    )
    return [
        Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"])
        for w in words
        if not (drop_white and _is_white(w.get("non_stroking_color")))
    ]


def group_lines(words: list[Word], tol: float = 3.0) -> list[Line]:
    """Cluster words into horizontal lines by their top coordinate."""
    lines: list[Line] = []
    for w in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(w.top - lines[-1].top) <= tol:
            lines[-1].words.append(w)
        else:
            lines.append(Line(w.top, [w]))
    for ln in lines:
        ln.words.sort(key=lambda w: w.x0)
    return lines


def _column_for(columns: list[Column], x: float) -> int | None:
    for c in columns:
        if c.left <= x < c.right:
            return c.index
    return None


def extract_grids(
    page,
    page_number: int,
    anchor_re: re.Pattern[str],
    header_label_words: frozenset[str] = frozenset(),
    min_anchors: int = 3,
    max_header_lines_above: int = 4,
    column_re: re.Pattern[str] | None = None,
    drop_white: bool = False,
) -> list[Grid]:
    """Extract every station x train matrix on a page, top to bottom.

    anchor_re          matches a train-number token; a line with many matches
                       is a table's header row and defines its columns.
    header_label_words upper-case words allowed in the label area of header
                       lines below the anchor row (e.g. STATIONS, TRAINS).
    column_re          optional second per-column header item (e.g. "12 CAR",
                       spaces removed). If a header line near the anchor row
                       has more of these than there are train numbers, some
                       numbers are unreadable (printed truncated: "4" for
                       90074); columns then come from that line, so a column
                       without a number is reported instead of having its
                       times read into its neighbours.

    A page usually holds one table, but some (the WR Dahanu sheet) stack an
    UP table under a DN table. Each table's body ends where the next table's
    header band begins.

    drop_white         ignore invisible (white) text; see page_words.
    """
    lines = group_lines(page_words(page, drop_white=drop_white))
    counts = [sum(1 for w in ln.words if anchor_re.fullmatch(w.text)) for ln in lines]
    best = max(counts, default=0)
    if best < min_anchors:
        return []
    # A second table's anchor row has a comparable number of trains; a stray
    # line quoting a few train numbers does not.
    threshold = max(min_anchors, math.ceil(0.5 * best))
    anchor_rows = [i for i, n in enumerate(counts) if n >= threshold]

    # (grid, last header line, first header line) per table, top to bottom.
    built: list[tuple[Grid, int, int]] = []
    lo = 0
    for ai in anchor_rows:
        if built and ai <= built[-1][1]:  # part of the previous header band
            continue
        centres = sorted(w.cx for w in lines[ai].words if anchor_re.fullmatch(w.text))
        if column_re is not None:
            for ln in lines[max(0, ai - 3): ai + 4]:
                alt = [cx for text, cx in _phrases_on(ln) if column_re.fullmatch(text)]
                if len(alt) > len(centres):
                    centres = sorted(alt)
        columns = _columns_at(centres)
        start = _header_start(lines, ai, columns, max(lo, ai - max_header_lines_above), header_label_words)
        grid, end = _build(lines, ai, start, columns, page_number, header_label_words, lo)
        built.append((grid, end, start))
        lo = end + 1
    for k, (grid, end, _) in enumerate(built):
        hi = built[k + 1][2] if k + 1 < len(built) else len(lines)
        _fill_body(grid, lines[end + 1 : hi])
    return [g for g, _, _ in built]


def extract_grid(page, page_number: int, anchor_re: re.Pattern[str], *args, **kwargs) -> Grid | None:
    """The first table on the page (kept for single-table callers)."""
    grids = extract_grids(page, page_number, anchor_re, *args, **kwargs)
    return grids[0] if grids else None


def _phrases_on(ln: Line) -> list[tuple[str, float]]:
    """Words joined by a plain space ("12" "CAR"), split at wider gaps.

    The limit is relative to the line's own tightest gap, because some sheets
    pack columns so closely that the gap between cells is barely wider than
    a space (WR 2018: 1.5pt inside "12 CAR", 3.9pt between columns).
    """
    out: list[tuple[str, float, float]] = []  # text, x0, x1
    gaps = [b.x0 - a.x1 for a, b in zip(ln.words, ln.words[1:]) if b.x0 - a.x1 > 0.2]
    tightest = min(gaps, default=0.0)
    for w in ln.words:
        gap_limit = min(0.6 * (w.bottom - w.top), 1.6 * tightest)
        if out and w.x0 - out[-1][2] <= gap_limit:
            text, x0, _ = out[-1]
            out[-1] = (text + w.text, x0, w.x1)
        else:
            out.append((w.text, w.x0, w.x1))
    return [(t.upper(), (a + b) / 2) for t, a, b in out]


def _columns(anchor_line: Line, anchor_re: re.Pattern[str]) -> list[Column]:
    return _columns_at(sorted(w.cx for w in anchor_line.words if anchor_re.fullmatch(w.text)))


def _columns_at(centers: list[float]) -> list[Column]:
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    pitch = median(gaps) if gaps else 40.0
    columns: list[Column] = []
    for i, cx in enumerate(centers):
        left = (centers[i - 1] + cx) / 2 if i > 0 else cx - pitch / 2
        # The last column gets extra room: vertical notes in it can be wider
        # than half a pitch and nothing lies to its right.
        right = (cx + centers[i + 1]) / 2 if i + 1 < len(centers) else cx + 0.8 * pitch
        columns.append(Column(i, cx, left, right))
    return columns


def _pitch(columns: list[Column]) -> float:
    gaps = [b.cx - a.cx for a, b in zip(columns, columns[1:])]
    return median(gaps) if gaps else 40.0


def _columns_hit(ln: Line, columns: list[Column]) -> int:
    label_right = columns[0].left
    return len({_column_for(columns, w.cx) for w in ln.words if w.cx >= label_right} - {None})


def _min_cols(columns: list[Column]) -> int:
    """Columns a line must touch to count as a header line (half, at least 2,
    but never more than there are: a sheet's last page may hold one train)."""
    return min(len(columns), max(2, math.ceil(0.5 * len(columns))))


def _header_start(lines: list[Line], ai: int, columns: list[Column], floor: int,
                  header_label_words: frozenset[str] = frozenset()) -> int:
    """First line of the header band: qualifying lines directly above the anchor.

    A line with other text in the label column (a station name such as
    "DAHANU ROAD") is a body row of the table above, never a header line:
    a row of next-working train numbers under a table must not swallow it.
    """
    start = ai
    for i in range(ai - 1, floor - 1, -1):
        labels = {w.text.upper() for w in lines[i].words if w.cx < columns[0].left}
        if labels and not labels <= header_label_words and not all(re.fullmatch(r"[\d.]+", x) for x in labels):
            break
        if _columns_hit(lines[i], columns) >= _min_cols(columns) and _crossing(lines[i], columns) <= 0.25:
            start = i
        else:
            break
    return start


def _crossing(ln: Line, columns: list[Column]) -> float:
    """Share of a line's words that spill across a column edge.

    Header cells (codes, car counts) sit inside their column; a page title
    that happens to span many columns ("VIRAR- CHURCHGATE ( UP )") does not.
    Measured on every WR release 2017-2026: titles >= 0.3, header lines
    <= 0.15 (two touching cells printed as one word).
    """
    words = [w for w in ln.words if w.cx >= columns[0].left and _column_for(columns, w.cx) is not None]
    if not words:
        return 1.0
    spill = sum(1 for w in words
                if w.x0 < columns[_column_for(columns, w.cx)].left - 1
                or w.x1 > columns[_column_for(columns, w.cx)].right + 1)
    return spill / len(words)


def _build(lines, ai, start, columns, page_number, header_label_words, lo) -> tuple[Grid, int]:
    """Header band from `start` down; returns the grid (no body yet) and the band's last line."""
    label_left, label_right = _label_band(lines, ai, columns)
    is_label = lambda w: label_left <= w.cx < label_right  # noqa: E731
    end = ai
    for i in range(ai + 1, len(lines)):
        ln = lines[i]
        labels = {w.text.upper() for w in ln.words if is_label(w)}
        if labels and not labels <= header_label_words:
            break
        if _columns_hit(ln, columns) >= _min_cols(columns):
            end = i
        else:
            break

    header_label_parts: list[str] = [ln.text for ln in lines[lo:start]]  # titles above
    for ln in lines[start : end + 1]:
        header_label_parts.append(" ".join(w.text for w in ln.words if is_label(w)))
        per_col: dict[int, list[Word]] = {}
        for w in ln.words:
            if is_label(w):
                continue
            c = _column_for(columns, w.cx)
            if c is not None:
                per_col.setdefault(c, []).append(w)
        for col in columns:
            col.header.append(per_col.get(col.index, []))

    return Grid(
        page_number=page_number,
        columns=columns,
        rows=[],
        header_label=" | ".join(p for p in header_label_parts if p),
        label_right=label_right,
        pitch=_pitch(columns),
        unassigned=[],
        label_left=label_left,
    ), end


LABEL_COLUMN_WORD = "STATIONS"


def _label_band(lines: list[Line], ai: int, columns: list[Column]) -> tuple[float, float]:
    """x-range of the station-name column.

    Left of the first train column, unless the "STATIONS" heading near the
    anchor row sits between two train columns; then the columns either side
    are narrowed to one pitch and the band is the gap between them.
    """
    near = [w for ln in lines[max(0, ai - 3): ai + 4] for w in ln.words if w.text.upper() == LABEL_COLUMN_WORD]
    for w in near:
        k = sum(1 for c in columns if c.cx < w.cx)
        if 0 < k < len(columns) and columns[k - 1].right > w.cx:
            half = _pitch(columns) / 2
            columns[k - 1].right = columns[k - 1].cx + half
            columns[k].left = columns[k].cx - half
            return columns[k - 1].right, columns[k].left
    return float("-inf"), columns[0].left


def _fill_body(g: Grid, body_lines: list[Line]) -> None:
    """Body rows: every line between the header band and the next table."""
    for ln in body_lines:
        label = " ".join(w.text for w in ln.words if g.is_label(w))
        cells: dict[int, list[Word]] = {}
        for w in ln.words:
            if g.is_label(w):
                continue
            c = _column_for(g.columns, w.cx)
            if c is None:
                g.unassigned.append(w)
            else:
                cells.setdefault(c, []).append(w)
        g.rows.append(Row(label=label, top=ln.top, cells=cells))
