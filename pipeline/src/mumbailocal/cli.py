"""Command line entry point.

  mumbailocal wr <pdf-dir> [--json out.json] [--db out.sqlite] [--diag out.json]
                 [--previous <pdf-dir>] [--strict]
  mumbailocal cr <pdf-dir> [same options]          Main, Harbour, Trans-Harbour, Port, Pune
  mumbailocal ntes-fetch <out-dir>                 save NTES schedule pages (Vasai-Diva-Panvel, Matheran)
  mumbailocal ntes <raw-dir> [same options]        parse saved NTES pages
  mumbailocal build --wr <pdf-dir> --cr <pdf-dir> [--ntes <raw-dir>] [same options]   one DB
  mumbailocal platforms --db out.sqlite --yatri yatri.db [--stats s.json] [--strict]
  mumbailocal release --db out.sqlite --out <dir> [--tag T] [--local | --merge-layers]

--strict refuses to write the database when the release gate says HOLD
(exit status 2), so a layout change can never replace good data with bad.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from . import build_db, ntes as ntes_client, platforms, quality, release
from .model import Diagnostics, Train
from .sources import cr, ntes, wr


def _summary(trains, diag: Diagnostics | None = None) -> str:
    lines = [
        f"trips {len(trains)}  ({dict(Counter(t.direction for t in trains))})",
        f"stops {sum(len(t.stops) for t in trains)}",
        f"fast {sum(bool(t.is_fast) for t in trains)}  ac {sum(t.is_ac for t in trains)}  "
        f"ladies {sum(t.ladies_special for t in trains)}",
        f"service days {dict(Counter(t.service.days for t in trains))}",
    ]
    if diag is not None:
        lines.append(f"diagnostics {diag.counts()}")
    return "\n".join(lines)


def _flat(by_line: dict[str, list[Train]]) -> list[Train]:
    return [t for ts in by_line.values() for t in ts]


def _sources(*dirs: Path) -> dict[str, str]:
    return {f"{d.parent.name}/{p.name}" if len(dirs) > 1 else p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for d in dirs for p in sorted(d.glob("*.pdf"))}


def _drop_cross_railway_copies(wr_trains: list[Train], cr_by_line: dict[str, list[Train]],
                               diag: Diagnostics) -> list[Train]:
    """WR prints the CR Harbour trains that run over its tracks. The Harbour
    sheet times them end to end, so its copy is kept; any difference between
    the two sheets is reported."""
    cr_keys = {(t.number, t.direction): t for ts in cr_by_line.values() for t in ts}
    kept = []
    for t in wr_trains:
        other = cr_keys.get((t.number, t.direction))
        # Labelled "C.R.GMN" on the WR sheet, or numbered in a CR series
        # (91491 "WBO 1": CSMT -> Borivali).
        if other is not None and (t.operator == "CR" or cr.home_line(t.number) in cr.LINES):
            mine = {s.station_code: s.time_min % 1440 for s in t.stops + t.external_stops}
            theirs = {s.station_code: s.time_min % 1440 for s in other.stops + other.external_stops}
            hm = lambda m: f"{m // 60:02d}:{m % 60:02d}"  # noqa: E731
            differ = [f"{c} WR {hm(mine[c])} vs {other.line} {hm(theirs[c])}"
                      for c in mine if c in theirs and mine[c] != theirs[c]]
            diag.add("cross-railway-copy-dropped", f"{t.number} {t.direction}",
                     f"WR {t.sources[0]} -> {other.line} {other.sources[0]}"
                     + (f"; differ: {'; '.join(differ)}" if differ else "; times agree"))
            continue
        kept.append(t)
    return kept


def _finish(args: argparse.Namespace, by_line: dict[str, list[Train]], diag: Diagnostics,
            previous: list[Train] | None, meta: dict[str, str]) -> int:
    trains = _flat(by_line)
    for line, ts in by_line.items():
        print(f"[{line}]")
        print("  " + _summary(ts).replace("\n", "\n  "))
    print(f"diagnostics {diag.counts()}")
    verdict = quality.check(trains, diag, previous)
    print(f"release gate: {verdict}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(
            {"lines": sorted(by_line), "sources": {k: json.loads(v) for k, v in meta.items() if k.endswith("_sources")},
             "trains": [asdict(t) for t in trains]}, indent=1))
    if args.diag:
        Path(args.diag).parent.mkdir(parents=True, exist_ok=True)
        Path(args.diag).write_text(json.dumps([asdict(i) for i in diag.issues], indent=1))
    if args.db and args.strict and not verdict.ok:
        print(f"not writing {args.db}: release gate says HOLD")
        return 2
    if args.db:
        build_db.build(Path(args.db), by_line, meta)
        print(f"wrote {args.db}")
    return 0


def cmd_wr(args: argparse.Namespace) -> int:
    pdf_dir = Path(args.pdf_dir)
    diag = Diagnostics()
    trains = wr.parse_dir(pdf_dir, diag)
    previous = wr.parse_dir(Path(args.previous), Diagnostics()) if args.previous else None
    sources = _sources(pdf_dir)
    return _finish(args, {"WR": trains}, diag, previous,
                   {"wr_source_dir": str(pdf_dir), "wr_sources": json.dumps(sources)})


def cmd_cr(args: argparse.Namespace) -> int:
    pdf_dir = Path(args.pdf_dir)
    diag = Diagnostics()
    by_line = cr.parse_dir(pdf_dir, diag)
    previous = _flat(cr.parse_dir(Path(args.previous), Diagnostics())) if args.previous else None
    return _finish(args, by_line, diag, previous,
                   {"cr_source_dir": str(pdf_dir), "cr_sources": json.dumps(_sources(pdf_dir))})


def cmd_ntes_fetch(args: argparse.Namespace) -> int:
    out = ntes_client.fetch(Path(args.out_dir))
    print(f"saved {len(list(out.glob('*.html')))} schedule pages in {out}")
    return 0


def cmd_ntes(args: argparse.Namespace) -> int:
    raw = Path(args.raw_dir)
    diag = Diagnostics()
    by_line = ntes.parse_dir(raw, diag)
    previous = _flat(ntes.parse_dir(Path(args.previous), Diagnostics())) if args.previous else None
    return _finish(args, by_line, diag, previous,
                   {"ntes_source_dir": str(raw), "ntes_sources": json.dumps(ntes.sources(raw))})


def cmd_build(args: argparse.Namespace) -> int:
    wr_dir, cr_dir = Path(args.wr), Path(args.cr)
    ntes_dir = Path(args.ntes) if args.ntes else None
    diag = Diagnostics()
    cr_by_line = cr.parse_dir(cr_dir, diag)
    wr_trains = _drop_cross_railway_copies(wr.parse_dir(wr_dir, diag), cr_by_line, diag)
    ntes_by_line = ntes.parse_dir(ntes_dir, diag) if ntes_dir else {}
    by_line = {"WR": wr_trains, **cr_by_line, **ntes_by_line}
    previous = None
    if args.previous_wr or args.previous_cr or args.previous_ntes:
        previous = (wr.parse_dir(Path(args.previous_wr), Diagnostics()) if args.previous_wr else wr_trains) + \
            (_flat(cr.parse_dir(Path(args.previous_cr), Diagnostics())) if args.previous_cr else _flat(cr_by_line)) + \
            (_flat(ntes.parse_dir(Path(args.previous_ntes), Diagnostics())) if args.previous_ntes else _flat(ntes_by_line))
    meta = {"wr_source_dir": str(wr_dir), "wr_sources": json.dumps(_sources(wr_dir)),
            "cr_source_dir": str(cr_dir), "cr_sources": json.dumps(_sources(cr_dir))}
    if ntes_dir:
        meta |= {"ntes_source_dir": str(ntes_dir), "ntes_sources": json.dumps(ntes.sources(ntes_dir))}
    return _finish(args, by_line, diag, previous, meta)


def cmd_platforms(args: argparse.Namespace) -> int:
    yatri = Path(args.yatri)
    source_meta = {}
    info = yatri.with_suffix(".json")
    if info.exists():
        y = json.loads(info.read_text())
        source_meta = {k: y[k] for k in ("version", "sha256", "data_updated_at", "fetched_at") if y.get(k)}
    stats_path = Path(args.stats) if args.stats else None
    previous = platforms.load_stats(stats_path) if stats_path else None
    stats, verdict = platforms.add_to_db(Path(args.db), yatri, source_meta, previous, args.strict)
    d = stats.as_dict()
    print(f"stops {d['stops']}: platform {d['matched']} ({d['coverage']:.1%}), "
          f"train not in Yatri {d['no_train']}, stop not in Yatri {d['no_stop']}, "
          f"no platform {d['no_platform']}, time differs {d['time_mismatch']}, bad value {d['bad_platform']}")
    print(f"door side set on {d['door_side_set']} stops; {d['door_side_conflicting_groups']} of "
          f"{d['door_side_groups']} station/platform/direction groups disagree")
    if d["unmapped_stations"]:
        print(f"our stations with no Yatri match: {d['unmapped_stations']}")
    print("weakest stations:", ", ".join(f"{c} {r:.0%} of {n}" for c, r, n in d["weakest_stations"][:6]))
    r = d["rakes"]
    print(f"rake links: {r['linked']} of {r['yatri_links']} confirmed ({r['agreement']:.1%}); "
          f"train not ours {r['no_train']}, ends elsewhere {r['other_station']}, turn time off {r['bad_gap']}, "
          f"no common day {r['no_common_day']}, ambiguous {r['ambiguous']}")
    print(f"platforms gate: {verdict}")
    if args.strict and not verdict.ok:
        print(f"not writing the platform and rake_next tables into {args.db}")
        return 2
    if stats_path:
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(d, indent=1))
    print(f"wrote platform and rake_next tables into {args.db} (local only)")
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    try:
        rel = release.make_release(Path(args.db), Path(args.out), args.tag, local=args.local,
                                   merge_layers=args.merge_layers)
    except release.LocalOnlyData as e:
        print(f"refusing to release: {e}")
        return 2
    manifest = json.loads((rel / "manifest.json").read_text())
    print(f"release {manifest['version']} -> {rel}  ({manifest['db']['size']:,} bytes gzip)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mumbailocal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("wr", help="parse Western Railway suburban PDFs")
    p.add_argument("pdf_dir")
    p.add_argument("--json")
    p.add_argument("--db")
    p.add_argument("--diag")
    p.add_argument("--previous", help="previous release directory, for the trip-count check")
    p.add_argument("--strict", action="store_true", help="exit 2 without writing --db if the gate says HOLD")
    p.set_defaults(func=cmd_wr)
    c = sub.add_parser("cr", help="parse Central Railway suburban PDFs (all CR lines)")
    c.add_argument("pdf_dir")
    for opt in ("--json", "--db", "--diag"):
        c.add_argument(opt)
    c.add_argument("--previous", help="previous release directory, for the trip-count check")
    c.add_argument("--strict", action="store_true", help="exit 2 without writing --db if the gate says HOLD")
    c.set_defaults(func=cmd_cr)
    f = sub.add_parser("ntes-fetch", help="save NTES schedule pages for the NTES lines")
    f.add_argument("out_dir", help="e.g. data/raw/ntes/<date>; pages already there are kept")
    f.set_defaults(func=cmd_ntes_fetch)
    n = sub.add_parser("ntes", help="parse saved NTES pages (Vasai-Diva-Panvel, Neral-Matheran)")
    n.add_argument("raw_dir")
    for opt in ("--json", "--db", "--diag"):
        n.add_argument(opt)
    n.add_argument("--previous", help="previous NTES snapshot, for the trip-count check")
    n.add_argument("--strict", action="store_true", help="exit 2 without writing --db if the gate says HOLD")
    n.set_defaults(func=cmd_ntes)
    b = sub.add_parser("build", help="parse WR, CR and NTES into one database")
    b.add_argument("--wr", required=True, help="WR release directory")
    b.add_argument("--cr", required=True, help="CR download directory")
    b.add_argument("--ntes", help="NTES snapshot directory (Vasai-Diva-Panvel, Neral-Matheran)")
    for opt in ("--json", "--db", "--diag", "--previous-wr", "--previous-cr", "--previous-ntes"):
        b.add_argument(opt)
    b.add_argument("--strict", action="store_true", help="exit 2 without writing --db if the gate says HOLD")
    b.set_defaults(func=cmd_build)
    r = sub.add_parser("release", help="package a built database as a downloadable release")
    r.add_argument("--db", required=True)
    r.add_argument("--out", required=True, help="releases directory; the release goes in <out>/<tag>/")
    r.add_argument("--tag", help="default: data-<YYYYMMDD>-<sha8 of the database>")
    r.add_argument("--local", action="store_true",
                   help="allow local-only layers (platforms); such a release must never be published")
    r.add_argument("--merge-layers", action="store_true",
                   help="allow local-only layers in a publishable release; only when publishing them is approved")
    r.set_defaults(func=cmd_release)
    q = sub.add_parser("platforms", help="add Yatri's platforms to a built database (local only)")
    q.add_argument("--db", required=True, help="built timetable database to add the platform table to")
    q.add_argument("--yatri", required=True, help="yatri.db extracted by tools/yatri_fetch.py")
    q.add_argument("--stats", help="coverage stats JSON; compared with the previous build, then rewritten")
    q.add_argument("--strict", action="store_true", help="exit 2 without writing if the platforms gate says HOLD")
    q.set_defaults(func=cmd_platforms)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
