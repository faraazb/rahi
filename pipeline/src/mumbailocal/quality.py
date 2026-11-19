"""Release gate: decide whether a freshly parsed timetable is safe to publish.

Timetable PDFs change layout between releases. The parser reports anything it
could not place as a diagnostic; this module sorts those into

  blocking  data is probably missing or misread - do not publish, keep the
            last good database and get a human to look
  review    published, but listed for a human (loose station matches, typo
            corrections, conflicts inside the source itself)

and compares the release with the previous one: a large swing in the number
of trips is treated as a parse failure until shown otherwise.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .model import Diagnostics, Train

BLOCKING = frozenset({
    "direction-unknown",      # a whole table dropped
    "direction-label-conflict",
    "page-without-grid",      # a page with no recognisable table
    "station-unknown",        # a row's times dropped
    "time-without-station",
    "column-without-number",  # a train dropped
    "header-token-unknown",
    "header-code-unknown",
    "times-not-monotonic",    # times read into the wrong rows or columns
    "train-too-few-stops",
    "cell-multiple-times",
    "word-outside-columns",
})

# A release whose trip count moves by more than this against the previous
# one is held back. Real revisions add or drop a few percent of services.
MAX_TRIP_SWING = 0.15


@dataclass
class Verdict:
    blocking: Counter = field(default_factory=Counter)
    review: Counter = field(default_factory=Counter)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blocking and not self.notes

    def __str__(self) -> str:
        lines = ["PASS" if self.ok else "HOLD (do not publish)"]
        if self.blocking:
            lines.append(f"  blocking: {dict(self.blocking)}")
        lines += [f"  {n}" for n in self.notes]
        if self.review:
            lines.append(f"  review:   {dict(self.review)}")
        return "\n".join(lines)


def check(trains: list[Train], diag: Diagnostics, previous: list[Train] | None = None) -> Verdict:
    v = Verdict()
    for issue in diag.issues:
        (v.blocking if issue.kind in BLOCKING else v.review)[issue.kind] += 1
    if not trains:
        v.notes.append("no trains parsed")
    if previous:
        swing = abs(len(trains) - len(previous)) / len(previous)
        if swing > MAX_TRIP_SWING:
            v.notes.append(f"trip count {len(previous)} -> {len(trains)} ({swing:.0%} change)")
    return v
