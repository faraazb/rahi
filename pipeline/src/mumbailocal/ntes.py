"""Client for NTES, the National Train Enquiry System (CRIS / Indian Railways).

The Diva/Panvel/Vasai MEMUs and the Matheran hill railway are national-timetable
trains, so no suburban PDF lists them. NTES publishes each train's schedule as a
plain HTML page; this module finds the trains and saves those pages unchanged,
so `sources/ntes.py` can parse them offline like any other raw source.

Low volume and read-only: one train-list GET, then one token GET and one POST
per train, a second apart. No API key, no captcha.

    data/raw/ntes/<date>/
        SOURCES.txt         train, fetched-at, URL (like the PDF downloads)
        train_list.txt      the NTES train-list entries that were selected
        <number>.html       the schedule page as served
"""

from __future__ import annotations

import html
import http.cookiejar
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://enquiry.indianrail.gov.in/mntes"
UA = "Mozilla/5.0 (X11; Linux x86_64) open-mumbai-local/0.1 (+public-interest timetable mirror)"
DELAY_S = 1.0

# Which NTES trains belong to which of our lines, by number. Checked against the
# names in NTES's train list on 2026-11-07: 610xx are the Vasai/Diva/Panvel/Roha/Pen
# MEMUs (61001/61002 run to Boisar), 6916x the Panvel - Vasai/Dahanu MEMUs, 521xx
# the Matheran hill railway (Neral or Aman Lodge - Matheran).
LINE_SERIES: dict[str, re.Pattern] = {
    "DVP": re.compile(r"^(610\d\d|6916[1-8])$"),
    "NM": re.compile(r"^521\d\d$"),
}
# A selected entry must also be a local service, not a stray express in the series.
KIND = re.compile(r"\b(MEMU|PASS|PASSENGER|DEMU)\b")


class Client:
    def __init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.opener.addheaders = [("User-Agent", UA), ("Referer", BASE + "/")]
        self._primed = False

    def get(self, url: str, data: dict | None = None) -> str:
        body = urllib.parse.urlencode(data).encode() if data else None
        with self.opener.open(urllib.request.Request(url, data=body), timeout=30) as r:
            return r.read().decode("utf-8", "ignore")

    def train_list(self) -> list[tuple[str, str]]:
        """(number, name) for every train NTES knows."""
        js = self.get(f"{BASE}/javascripts/train_data.js")
        return [(m.group(1), m.group(2).strip()) for m in re.finditer(r'"(\d{5})-\s*([^"]*)"', js)]

    def schedule_page(self, number: str) -> tuple[str, str]:
        """(url, html) of one train's schedule page."""
        if not self._primed:  # session cookies
            self.get(f"{BASE}/")
            self._primed = True
        token = self.get(f"{BASE}/GetCSRFToken?t={int(time.time() * 1000)}")
        m = re.search(r"name='([^']+)'\s+value='([^']+)'", token)
        if not m:
            raise RuntimeError(f"NTES returned no CSRF token: {token[:200]!r}")
        url = f"{BASE}/q?opt=TrainServiceSchedule&subOpt=main&trainNo={number}"
        page = self.get(url, {"trainNo": number, m.group(1): m.group(2)})
        if number not in page:
            raise RuntimeError(f"NTES schedule page for {number} does not mention the train")
        return url, page


def select(entries: list[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {line: [] for line in LINE_SERIES}
    for number, name in entries:
        for line, pattern in LINE_SERIES.items():
            if pattern.match(number) and KIND.search(name.upper()):
                out[line].append((number, name))
    return out


def fetch(out_dir: Path, client: Client | None = None, log=print) -> Path:
    """Save today's schedule pages for every selected train into out_dir.

    Pages already saved there are kept, so an interrupted run can be resumed."""
    client = client or Client()
    chosen = select(client.train_list())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "train_list.txt").write_text(
        "".join(f"{line}\t{n}\t{name}\n" for line, ts in chosen.items() for n, name in ts))
    listing = out_dir / "SOURCES.txt"
    sources = dict(re.findall(r"^(\S+)\t(.*)$", listing.read_text(), re.M)) if listing.exists() else {}
    for line, trains in chosen.items():
        log(f"{line}: {len(trains)} trains")
        for number, _ in trains:
            path = out_dir / f"{number}.html"
            if path.exists() and number in path.read_text():
                stamp = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
                sources.setdefault(path.name, f"{stamp}\t{BASE}/q?opt=TrainServiceSchedule&subOpt=main&trainNo={number}")
                continue
            url, page = client.schedule_page(number)
            path.write_text(page)
            stamp = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
            sources[path.name] = f"{stamp}\t{url}"
            listing.write_text("".join(f"{k}\t{v}\n" for k, v in sorted(sources.items())))
            time.sleep(DELAY_S)
    listing.write_text("".join(f"{k}\t{v}\n" for k, v in sorted(sources.items())))
    return out_dir


# ------------------------------------------------------------ schedule page

def _text(s: str) -> str:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def parse_page(page: str, number: str) -> dict:
    """The schedule page as a dict: name, days_of_run, type, travel_time, stops.

    Each stop: seq, station, code, day (1 = the day the train starts), arr, dep
    ("HH:MM" or None at the origin / destination), halt, km.
    """
    out: dict = {"train": number}
    m = re.search(r">\s*(%s\s+[^<]+?)\s*<" % number, page)
    out["name"] = m.group(1).strip() if m else None

    def field(label: str) -> str | None:
        m = re.search(label + r":\s*(?:&nbsp;)?\s*</span>\s*(?:<span[^>]*>)?\s*([^<]+)", page)
        return m.group(1).strip() if m else None

    out["days_of_run"] = field("Days of Run")
    out["type"] = field("Type")
    m = re.search(r"Travel Time</span>:\s*(?:&nbsp;)?\s*([0-9:]+)", page)
    out["travel_time"] = m.group(1) if m else None
    stops = []
    # Rows: Sr | Station<br>Code | Day | Arr<br>Dep | Halt | Dist
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)
        if len(tds) != 6:
            continue
        sr, stn, day, times, halt, dist = tds
        sr, day, halt, dist = _text(sr), _text(day), _text(halt), _text(dist)
        if not sr.isdigit():
            continue
        name_code = [_text(x) for x in re.split(r"<br\s*/?>", stn, flags=re.I)]
        arr_dep = [_text(x) for x in re.split(r"<br\s*/?>", times, flags=re.I)] + [""]
        stops.append({
            "seq": int(sr),
            "station": name_code[0],
            "code": name_code[1] if len(name_code) > 1 else None,
            "day": int(day) if day.isdigit() else None,
            "arr": None if arr_dep[0] in ("SRC", "") else arr_dep[0],
            "dep": None if arr_dep[1] in ("DSTN", "") else arr_dep[1],
            "halt": halt or None,
            "km": int(dist) if dist.isdigit() else None,
        })
    out["stops"] = stops
    return out
