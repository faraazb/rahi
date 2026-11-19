#!/usr/bin/env python3
"""Compare one line of our parsed timetable with Yatri's bundled database.

Development check only: Yatri's data is read locally as a reference and never
copied into our output. Our PDFs may be an older timetable revision than
Yatri's snapshot, so every train is classified to separate "timetable changed"
from "parser got it wrong":

  identical      same stations, every time equal
  within-1min    same stations, every time within 1 minute
  shifted        same stations, every time moved by the same amount (retimed)
  times-differ   same stations, mixed time differences
  stops-differ   station sets differ (added/removed halts)

Usage: compare_yatri.py OUR.sqlite YATRI.db [--line WR|CR|HR|THR|UR|PUNE]
                        [--examples N] [--details out.tsv]

--details writes one row per train that is not identical or whose flags
differ, for writing up docs/observations.md.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from collections import Counter, defaultdict

from mumbailocal.stations import StationTable

SERVICE_DAY_START = 180
# Our line code -> Yatri's local_lines.id
YATRI_LINE = {"CR": "1", "WR": "2", "HR": "3", "THR": "4", "UR": "5", "DVP": "6", "NM": "7", "PUNE": "8"}
# Yatri train_exception_days.id -> (days, not_on_holidays) as we store them.
# 5-7 ("General on Sunday/Holidays" etc.) describe an AC rake turning
# ordinary, not running days.
YATRI_DAYS = {None: ("1111111", 0), 0: ("1111111", 0), 1: ("1111110", 1), 2: ("1111100", 1),
              3: ("1111110", 0), 4: ("1111100", 0), 5: ("1111111", 0), 6: ("1111111", 0),
              7: ("1111111", 0)}
YATRI_MARK = {1: "X", 2: "XX", 3: "Y", 4: "YY", 5: "#", 6: "##", 7: "###"}


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def clock_order(stops: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Stops in running order from clock times alone.

    A suburban trip runs for well under 12 hours, so after sorting by time of
    day the largest gap on the 24-hour circle separates its end from its start.
    """
    s = sorted(stops, key=lambda x: x[1] % 1440)
    if len(s) < 2:
        return s
    gaps = [((s[(i + 1) % len(s)][1] - s[i][1]) % 1440, i) for i in range(len(s))]
    _, i = max(gaps)
    return s[i + 1:] + s[: i + 1]


def normalise(times: list[int]) -> list[int]:
    out, offset, prev = [], 0, None
    for t in times:
        t += offset
        if prev is not None and t < prev - 720:
            offset += 1440
            t += 1440
        out.append(t)
        prev = t
    if out and out[0] < SERVICE_DAY_START:
        out = [t + 1440 for t in out]
    return out


def load_ours(path: str, line: str):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    trains = defaultdict(list)  # (number, dir) -> [trip]
    rows = db.execute("""
        SELECT t.id, t.number, t.variant, t.direction, t.is_fast, t.is_ac, t.ac_weekdays_only,
               t.ladies_special, t.cars, sv.days, sv.not_on_holidays, s.code, st.time_min
        FROM train t JOIN line l ON l.id=t.line_id JOIN service sv ON sv.id=t.service_id
        JOIN stop_time st ON st.train_id=t.id JOIN station s ON s.id=st.station_id
        WHERE l.code=? ORDER BY t.id, st.seq""", (line,))
    trips = {}
    for tid, num, var, d, fast, ac, acw, ladies, cars, days, noh, code, tm in rows:
        if tid not in trips:
            trips[tid] = dict(number=num, variant=var, dir=d, fast=fast, ac=ac, acw=acw, ladies=ladies,
                              cars=cars, days=days, noh=noh, stops={})
            trains[(num, d)].append(trips[tid])
        trips[tid]["stops"][code] = tm
    return trains


def load_yatri(path: str, line_id: str, table: StationTable):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    st = {sid: (code, name) for sid, code, name in db.execute("SELECT ls_id, code, name FROM local_stations")}
    props = defaultdict(set)
    for pid, num in db.execute("SELECT property_id, train_number FROM local_train_properties WHERE deleted_at IS NULL"):
        props[num].add(str(pid))
    trains = {}
    for num, speed, coaches, d, exid in db.execute(
            "SELECT number, speed, coaches, direction_id, exception_day_id FROM local_trains "
            "WHERE line_id=? AND deleted_at IS NULL", (line_id,)):
        exid = None if exid in (None, "", "NULL") else int(exid)
        trains[(num, int(d))] = dict(fast=speed == "F", cars=int(float(coaches)) if coaches else None,
                                     exc=exid, ac="1" in props[num], ladies="2" in props[num], stops=[])
    for num, sid, tm in db.execute(
            "SELECT s.local_train_number, s.station_id, s.time FROM local_train_schedule s "
            "JOIN local_trains t ON t.number=s.local_train_number WHERE t.line_id=? AND s.deleted_at IS NULL",
            (line_id,)):
        h, m = map(int, tm.split(":")[:2])
        code = st[sid][0] if sid in st else f"?{sid}"
        for key in ((num, 1), (num, 2)):
            if key in trains:
                trains[key]["stops"].append((code, h * 60 + m))
    used = {code for t in trains.values() for code, _ in t["stops"]}
    names = {code: name for code, name in st.values() if code in used}
    # Yatri codes -> ours: by our station aliases first, so code spelling
    # (D vs DR) is reported once and not as a timetable difference.
    to_ours = {}
    for code, name in names.items():
        hit = table.lookup(name) or table.by_code.get(code)
        to_ours[code] = hit.code if hit else code
    for t in trains.values():
        raw = clock_order([(to_ours.get(c, c), tm) for c, tm in t["stops"]])
        times = normalise([x[1] for x in raw])
        t["stops"] = {code: tm for (code, _), tm in zip(raw, times)}
    return trains, names, to_ours


def classify(ours: dict, theirs: dict) -> tuple[str, list[int]]:
    common = ours.keys() & theirs.keys()
    diffs = [ours[c] - theirs[c] for c in common]
    if ours.keys() != theirs.keys():
        return "stops-differ", diffs
    if all(d == 0 for d in diffs):
        return "identical", diffs
    if all(abs(d) <= 1 for d in diffs):
        return "within-1min", diffs
    if len(set(diffs)) == 1:
        return "shifted", diffs
    return "times-differ", diffs


def flag_diffs(b: dict, y: dict) -> list[str]:
    out = []
    if bool(b["fast"]) != y["fast"]:
        out.append(f"fast ours={bool(b['fast'])} yatri={y['fast']}")
    if y["cars"] in (12, 15) and b["cars"] is not None and b["cars"] != y["cars"]:
        out.append(f"cars ours={b['cars']} yatri={y['cars']}")
    if y["cars"] == 15 and b["cars"] is None:
        out.append("cars ours=? yatri=15")
    want = YATRI_DAYS.get(y["exc"])
    if want and (b["days"], b["noh"]) != want:
        out.append(f"days ours={b['days']}{'+hol' if b['noh'] else ''} yatri={YATRI_MARK.get(y['exc'], y['exc'])}")
    if bool(b["ac"]) != y["ac"]:
        out.append(f"ac ours={bool(b['ac'])} yatri={y['ac']}")
    if y["exc"] == 7 and b["ac"] and not b["acw"]:
        out.append("ac-weekend ours=AC every day yatri=### (ordinary Sat/Sun)")
    if b["acw"] and y["exc"] not in (5, 6, 7):
        out.append(f"ac-weekend ours=ordinary Sat/Sun yatri={YATRI_MARK.get(y['exc'], 'no mark')}")
    if bool(b["ladies"]) != y["ladies"]:
        out.append(f"ladies ours={bool(b['ladies'])} yatri={y['ladies']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ours")
    ap.add_argument("yatri")
    ap.add_argument("--line", default="WR", choices=sorted(YATRI_LINE))
    ap.add_argument("--examples", type=int, default=5)
    ap.add_argument("--details", help="write per-train differences as TSV")
    a = ap.parse_args()

    table = StationTable(a.line)
    ours = load_ours(a.ours, a.line)
    yatri, y_names, to_ours = load_yatri(a.yatri, YATRI_LINE[a.line], table)
    suburban = {k: v for k, v in yatri.items() if re.fullmatch(r"\d{5}[A-Z]?", k[0])}
    print(f"Yatri line {YATRI_LINE[a.line]} ({a.line}): {len(yatri)} trains, {len(suburban)} with suburban numbers "
          f"(excluded: {sorted({k[0][:3] for k in yatri.keys() - suburban.keys()})})")
    print(f"Ours: {sum(len(v) for v in ours.values())} trips, {len(ours)} (number, direction) keys")

    print("\n== Station codes (Yatri -> ours, matched by name)")
    diff = sorted((y, o) for y, o in to_ours.items() if o != y and o in table.by_code)
    print("   " + ", ".join(f"{y}->{o}" for y, o in diff))
    unmatched = sorted(f"{y} ({y_names[y]})" for y, o in to_ours.items() if o not in table.by_code)
    print(f"   Yatri stations not on our {a.line} table: {unmatched}")

    # A train can be filed in the other direction (Panvel -> Goregaon via
    # Vadala): match on the number alone when the direction differs.
    by_num = defaultdict(list)
    for k in suburban:
        by_num[k[0]].append(k)
    pairs_keys = []
    dir_diff = []
    for key in sorted(ours):
        if key in suburban:
            pairs_keys.append((key, key))
        elif len(by_num.get(key[0], [])) == 1 and (key[0], 3 - key[1]) not in ours:
            pairs_keys.append((key, by_num[key[0]][0]))
            dir_diff.append(key[0])
    # Numbered differently (Yatri files the Pune locals as 01551..01592, the
    # sheets print 99801..): pair what is left by direction, first station
    # and departure time when that is unique on both sides.
    renumbered = []
    def start(stops):
        code = min(stops, key=stops.get)
        return code, stops[code]
    left_o = defaultdict(list)
    for k in ours:
        if k not in {ok for ok, _ in pairs_keys} and len(ours[k]) == 1:
            left_o[(k[1], *start(ours[k][0]["stops"]))].append(k)
    left_y = defaultdict(list)
    for k, y in suburban.items():
        if k not in {yk for _, yk in pairs_keys} and y["stops"]:
            left_y[(k[1], *start(y["stops"]))].append(k)
    for sig, oks in left_o.items():
        if len(oks) == 1 and len(left_y.get(sig, [])) == 1:
            pairs_keys.append((oks[0], left_y[sig][0]))
            renumbered.append(f"{oks[0][0]}={left_y[sig][0][0]}")
    matched_y = {yk for _, yk in pairs_keys}
    only_ours = sorted(k for k in ours if k not in {ok for ok, _ in pairs_keys})
    only_yatri = sorted(k for k in suburban if k not in matched_y)
    print(f"\n== Coverage: common {len(pairs_keys)}, only ours {len(only_ours)}, only Yatri {len(only_yatri)}")
    if dir_diff:
        print(f"   matched across directions (ours vs Yatri disagree on UP/DN): {dir_diff}")
    if renumbered:
        print(f"   matched by first departure, numbers differ (ours=Yatri): {' '.join(renumbered)}")

    cls = Counter()
    examples = defaultdict(list)
    stop_total = stop_exact = 0
    flag_all, flag_stable = Counter(), Counter()
    details = []
    hm = lambda m: f"{m // 60 % 24:02d}:{m % 60:02d}"  # noqa: E731
    for okey, ykey in pairs_keys:
        y = suburban[ykey]
        best = min(ours[okey], key=lambda t: sum(abs(t["stops"].get(c, 9999) - tm) for c, tm in y["stops"].items()))
        c, diffs = classify(best["stops"], y["stops"])
        cls[c] += 1
        examples[c].append((okey, best, y, diffs))
        stop_total += len(diffs)
        stop_exact += sum(d == 0 for d in diffs)
        fd = flag_diffs(best, y)
        for f in fd:
            flag_all[f.split()[0] + " differ"] += 1
            if c in ("identical", "within-1min"):
                flag_stable[f.split()[0] + " differ"] += 1
        if c != "identical" or fd:
            common = best["stops"].keys() & y["stops"].keys()
            td = "; ".join(f"{s} {hm(best['stops'][s])}/{hm(y['stops'][s])}" for s in sorted(
                common, key=lambda s: best["stops"][s]) if best["stops"][s] != y["stops"][s])
            details.append([okey[0] + (f"={ykey[0]}" if ykey[0] != okey[0] else ""), "UP" if okey[1] == 1 else "DN", c,
                            hm(min(best["stops"].values())), hm(min(y["stops"].values())),
                            ",".join(sorted(best["stops"].keys() - y["stops"].keys(), key=lambda s: best["stops"][s])),
                            ",".join(sorted(y["stops"].keys() - best["stops"].keys(), key=lambda s: y["stops"][s])),
                            td, " | ".join(fd)])

    n = sum(cls.values()) or 1
    print(f"\n== Per-train comparison ({sum(cls.values())} common trains)")
    for k in ("identical", "within-1min", "shifted", "times-differ", "stops-differ"):
        print(f"   {k:13s} {cls[k]:5d}  {100 * cls[k] / n:5.1f}%")
    print(f"   stop-times at common stations: {stop_exact}/{stop_total} exact "
          f"({100 * stop_exact / max(stop_total, 1):.1f}%)")
    print("\n== Flag differences, all common trains:", dict(sorted(flag_all.items())))
    print("== Flag differences, trains with matching times only:", dict(sorted(flag_stable.items())))

    for k in ("within-1min", "shifted", "times-differ", "stops-differ"):
        if not examples[k]:
            continue
        print(f"\n-- examples: {k}")
        for (num, d), b, y, diffs in examples[k][: a.examples]:
            only_o = sorted(b["stops"].keys() - y["stops"].keys())
            only_y = sorted(y["stops"].keys() - b["stops"].keys())
            dd = Counter(diffs).most_common(4)
            print(f"   {num} dir{d}: ours {hm(min(b['stops'].values()))} {len(b['stops'])} stops, "
                  f"yatri {hm(min(y['stops'].values()))} {len(y['stops'])} stops; "
                  f"diff(min):count {dd}; only-ours {only_o} only-yatri {only_y}")

    print(f"\n-- only in Yatri ({len(only_yatri)}):", " ".join(f"{k[0]}{'U' if k[1] == 1 else 'D'}" for k in only_yatri))
    print(f"-- only ours ({len(only_ours)}):", " ".join(f"{k[0]}{'U' if k[1] == 1 else 'D'}" for k in only_ours))
    if a.details:
        with open(a.details, "w") as f:
            f.write("number\tdir\tclass\tours_first\tyatri_first\tonly_ours\tonly_yatri\ttime_diffs(ours/yatri)\tflags\n")
            for row in details:
                f.write("\t".join(row) + "\n")
        print(f"\nwrote {len(details)} rows to {a.details}")


if __name__ == "__main__":
    main()
