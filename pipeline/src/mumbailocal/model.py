"""Source-neutral records every parser emits and the loader consumes."""

from __future__ import annotations

from dataclasses import dataclass, field

# Service-day flags, Monday first: "1111110" = every day except Sunday.
ALL_DAYS = "1111111"
NOT_SUNDAY = "1111110"
SUNDAY_ONLY = "0000001"


@dataclass
class Stop:
    station_code: str
    station_label: str  # exactly as printed, for traceability
    # Minutes after 00:00 of the service day. Values >= 1440 belong to the
    # small hours after midnight (GTFS convention).
    time_min: int
    markers: list[str] = field(default_factory=list)
    # Arrival, when the source gives one apart from the departure in time_min
    # (NTES: "06:45 / 07:00" at Vasai Road). Same clock as time_min.
    arr_min: int | None = None


@dataclass
class Service:
    days: str = ALL_DAYS
    not_on_holidays: bool = False


@dataclass
class Train:
    number: str
    line: str  # line code, e.g. "WR"
    direction: str  # "UP" (towards the city terminus) or "DN"
    # The PTT sometimes prints one number on two different trips; the second
    # and later trips in the same sheet get variant 1, 2, ...
    variant: int = 0
    origin: str | None = None  # station code
    destination: str | None = None
    cars: int | None = None
    is_ac: bool = False
    ac_weekdays_only: bool = False  # AC Mon-Fri, ordinary rake Sat/Sun
    ladies_special: bool = False
    is_fast: bool | None = None
    service: Service = field(default_factory=Service)
    notes: list[str] = field(default_factory=list)  # raw phrases as printed
    unrecognized_notes: list[str] = field(default_factory=list)
    # Stations the sheet marks as passed without a halt, e.g. "P@ADH".
    pass_marks: list[str] = field(default_factory=list)
    # Terminal printed in the header but with no time in its cell.
    terminal_without_time: str | None = None
    stops: list[Stop] = field(default_factory=list)
    # Timed terminals off this line, e.g. CSMT for Harbour trains printed on
    # the WR sheet ("EX CSMT 04:28"). Before stops[0] if origin, after
    # stops[-1] if destination.
    external_stops: list[Stop] = field(default_factory=list)
    # Railway that runs the train when it is not the sheet's own, e.g. "CR".
    operator: str | None = None
    sources: list[str] = field(default_factory=list)  # "file#page"


@dataclass
class Issue:
    kind: str
    where: str
    detail: str


@dataclass
class Diagnostics:
    issues: list[Issue] = field(default_factory=list)

    def add(self, kind: str, where: str, detail: str = "") -> None:
        self.issues.append(Issue(kind, where, detail))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.issues:
            out[i.kind] = out.get(i.kind, 0) + 1
        return dict(sorted(out.items()))
