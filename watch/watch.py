#!/usr/bin/env python3
"""Detect new or changed suburban timetable PDFs on the railway websites.

Standard library only, so the GitHub Action needs no install step.

For one railway (wr / cr) it:
  1. fetches each index page, trying the hosts in sources.json in order
     (primary site first, then the old-site mirror);
  2. collects the PDF links and HEADs each one (ETag / Last-Modified / length);
  3. compares them with watch/state/<railway>.json, keyed by URL path so a host
     switch is not mistaken for a new timetable;
  4. if anything was added, removed or modified, downloads a full snapshot of the
     railway's current PDFs into data/raw/<railway>/<date>/ and rewrites the state.
     Each PDF is saved under the sheet name the parser expects (dn.pdf, hb_up.pdf,
     ...), chosen by the "sheets" rules in sources.json; PDFs that are not a sheet,
     or that no rule matches, go to other/ where the parser does not look.
     SOURCES.txt keeps every file's original URL (the w.e.f. date is in its name).

It never treats an unreachable page or a 404 PDF as "removed": failures are
reported as errors and that page's previous state is kept.

Outputs (in --out): result.json (machine-readable), report.md (PR body),
errors.md (issue body).
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import html.parser
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = "rahi-timetable-watch/1.0 (open-source Mumbai local timetable; github.com/faraazb/rahi)"
TIMEOUT = 60
ATTEMPTS = 3


# --------------------------------------------------------------------------- http

class RelayError(RuntimeError):
    """The relay itself refused or failed (not a railway response)."""


def _relayed(url: str, headers: dict) -> tuple[str, dict]:
    """Route through the relay (relay/) when WATCH_RELAY_URL is set: GitHub's
    runners cannot reach the railway sites, a function in Mumbai can."""
    relay = os.environ.get("WATCH_RELAY_URL", "").strip()
    if not relay:
        return url, headers
    return (f"{relay}?url={urllib.parse.quote(url, safe='')}",
            {**headers, "X-Relay-Secret": os.environ.get("WATCH_RELAY_SECRET", "").strip()})


def _response_headers(h) -> dict:
    """Lower-cased headers; through the relay, the railway's are x-upstream-<name>."""
    out = {k.lower(): v for k, v in h.items()}
    if "x-relay-error" in out:
        raise RelayError(f"relay: {out['x-relay-error']}")
    for k, v in list(out.items()):
        if k.startswith("x-upstream-"):
            out[k.removeprefix("x-upstream-")] = v
    return out


def _request(url: str, method: str = "GET") -> tuple[int, dict, bytes]:
    """Return (status, headers, body). Retries network errors and 5xx."""
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        if attempt:
            time.sleep(5 * attempt)
        target, headers = _relayed(url, {"User-Agent": UA})
        req = urllib.request.Request(target, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read() if method == "GET" else b""
                return r.status, _response_headers(r.headers), body
        except urllib.error.HTTPError as e:
            h = {k.lower(): v for k, v in e.headers.items()}
            if "x-relay-error" in h and e.code in (400, 401):
                raise RelayError(f"relay: {h['x-relay-error']} (HTTP {e.code}); check WATCH_RELAY_URL/SECRET")
            if e.code < 500:
                return e.code, _response_headers(e.headers), b""
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
    raise RuntimeError(f"{method} {url} failed after {ATTEMPTS} attempts: {last}")


class _Links(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def pdf_links(page_html: str, page_url: str, hosts: list[str], host: str) -> list[dict]:
    """PDF links on the page, rewritten onto the host that actually served it."""
    p = _Links()
    p.feed(page_html)
    out: dict[str, dict] = {}
    for href, text in p.links:
        href = html.unescape(href).strip()
        u = urllib.parse.urlsplit(urllib.parse.urljoin(page_url, href))
        if not u.path.lower().endswith(".pdf"):
            continue
        netloc = host if u.netloc in hosts else u.netloc
        # Canonical path: percent-encoded consistently, whatever the page used.
        path = urllib.parse.quote(urllib.parse.unquote(u.path), safe="/'()")
        url = urllib.parse.urlunsplit(("https", netloc, path, u.query, ""))
        key = path + (("?" + u.query) if u.query else "")
        if key not in out or (text and not out[key]["title"]):
            out[key] = {"key": key, "url": url, "title": text,
                        "name": urllib.parse.unquote(path.rsplit("/", 1)[-1])}
    return list(out.values())


# ------------------------------------------------------------------------- check

def check_page(page: dict, hosts: list[str], errors: list[str]) -> tuple[str | None, list[dict] | None]:
    """Find a host that serves the page with enough PDF links."""
    tried = []
    for host in hosts:
        url = f"https://{host}{page['path']}"
        try:
            status, _, body = _request(url)
        except RuntimeError as e:
            tried.append(f"{host}: {e}")
            continue
        if status != 200:
            tried.append(f"{host}: HTTP {status}")
            continue
        links = pdf_links(body.decode("utf-8", "replace"), url, hosts, host)
        if len(links) < page["min_pdfs"]:
            tried.append(f"{host}: only {len(links)} PDF links (expected >= {page['min_pdfs']}); "
                         "page structure may have changed")
            continue
        return host, links
    errors.append(f"**{page['id']}** ({page['title']}): no host served the index page.\n"
                  + "".join(f"  - {t}\n" for t in tried))
    return None, None


def head(link: dict) -> dict:
    status, h, _ = _request(link["url"], "HEAD")
    if status in (405, 501):  # HEAD not allowed: fall back to GET
        status, h, body = _request(link["url"])
        h.setdefault("content-length", str(len(body)))
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    ctype = h.get("content-type", "")
    if "pdf" not in ctype and "octet-stream" not in ctype:
        raise RuntimeError(f"unexpected content-type {ctype!r} (an error page?)")
    return {"etag": h.get("etag"), "last_modified": h.get("last-modified"),
            "length": int(h["content-length"]) if h.get("content-length") else None}


def download(url: str) -> bytes:
    status, h, body = _request(url)
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    if not body.startswith(b"%PDF"):
        raise RuntimeError("response is not a PDF")
    return body


def http_date(s: str | None) -> dt.date | None:
    try:
        return email.utils.parsedate_to_datetime(s).date() if s else None
    except (TypeError, ValueError):
        return None


def sheet_names(rules: list[dict], current: list[tuple[str, dict]]) -> tuple[dict[str, str], list[str], list[str]]:
    """Where each live PDF is saved in the snapshot: {key: relative path}.

    The first rule whose regex matches the PDF's website name decides; save_as null
    means "not a sheet". Returns (paths, unclassified names, conflict notes)."""
    paths: dict[str, str] = {}
    unclassified: list[str] = []
    claims: dict[str, list[dict]] = {}
    for _, c in current:
        rule = next((r for r in rules if re.search(r["match"], c["name"], re.IGNORECASE)), None)
        if rule is None:
            unclassified.append(c["name"])
        if rule is None or not rule["save_as"]:
            paths[c["key"]] = f"other/{c['name']}"
        else:
            claims.setdefault(rule["save_as"], []).append(c)
    conflicts = []
    for sheet, cs in claims.items():
        cs.sort(key=lambda c: http_date(c["entry"].get("last_modified")) or dt.date.min, reverse=True)
        paths[cs[0]["key"]] = sheet
        for c in cs[1:]:
            paths[c["key"]] = f"other/{c['name']}"
        if len(cs) > 1:
            conflicts.append(f"{len(cs)} PDFs look like `{sheet}`; kept the newest, `{cs[0]['name']}`, and moved "
                             + ", ".join(f"`{c['name']}`" for c in cs[1:]) + " to other/.")
    return paths, unclassified, conflicts


def run(railway: str, sources: dict, state_path: pathlib.Path, snapshot_root: pathlib.Path,
        out: pathlib.Path, forget: list[str]) -> dict:
    cfg = sources[railway]
    today = dt.date.today().isoformat()
    old = json.loads(state_path.read_text()) if state_path.exists() else {"railway": railway, "pages": {}}
    if forget:  # testing aid: pretend matching files were never seen
        for pg in old["pages"].values():
            for k in [k for k in pg["files"] if any(f in k or f == "*" for f in forget)]:
                del pg["files"][k]

    errors: list[str] = []
    notes: list[str] = []
    new = {"railway": railway, "pages": {}}
    rows: list[dict] = []  # for the report
    current: list[tuple[str, dict]] = []  # (page_id, link+meta) of everything live now

    for page in cfg["pages"]:
        pid = page["id"]
        prev = old["pages"].get(pid, {"host": None, "files": {}})
        host, links = check_page(page, cfg["hosts"], errors)
        if links is None:
            new["pages"][pid] = prev  # keep last known good
            continue
        if prev.get("host") and prev["host"] != host:
            notes.append(f"{pid}: now served by `{host}` (was `{prev['host']}`).")
        files: dict[str, dict] = {}
        for link in links:
            before = prev["files"].get(link["key"])
            try:
                meta = head(link)
            except RuntimeError as e:
                errors.append(f"**{pid}**: linked PDF unreachable: [{link['name']}]({link['url']}) - {e}")
                if before:
                    files[link["key"]] = before
                continue
            entry = {"name": link["name"], "title": link["title"], **meta,
                     "sha256": before.get("sha256") if before else None,
                     "first_seen": before.get("first_seen", today) if before else today}
            if before is None:
                status = "added"
            elif (before.get("length"), before.get("last_modified"), before.get("etag")) != \
                    (meta["length"], meta["last_modified"], meta["etag"]):
                status = "modified?"  # confirmed by hash after download
            else:
                status = "unchanged"
            files[link["key"]] = entry
            current.append((pid, {**link, "status": status, "entry": entry}))
        for key, before in prev["files"].items():
            if key not in files and not any(key == c[1]["key"] for c in current):
                rows.append({"page": pid, "status": "removed", "name": before["name"],
                             "title": before.get("title", ""), "url": None, "entry": before})
        new["pages"][pid] = {"host": host, "files": files}

    # Download everything live if anything might have changed, so the snapshot is complete.
    suspects = [c for c in current if c[1]["status"] != "unchanged"]
    removed = [r for r in rows if r["status"] == "removed"]
    changed = False
    snapshot_dir = None
    saved_as, unclassified, conflicts = sheet_names(cfg.get("sheets", []), current)
    if suspects or removed:
        blobs: dict[str, bytes] = {}
        for pid, c in current:
            try:
                blobs[c["key"]] = download(c["url"])
            except RuntimeError as e:
                errors.append(f"**{pid}**: download failed: [{c['name']}]({c['url']}) - {e}")
        for pid, c in current:
            e = c["entry"]
            if c["key"] not in blobs:
                if c["status"] != "unchanged":  # retry tomorrow: keep old state
                    prev_e = old["pages"].get(pid, {}).get("files", {}).get(c["key"])
                    if prev_e:
                        new["pages"][pid]["files"][c["key"]] = prev_e
                    else:
                        new["pages"][pid]["files"].pop(c["key"], None)
                    c["status"] = "failed"
                continue
            sha = hashlib.sha256(blobs[c["key"]]).hexdigest()
            if c["status"] == "modified?":
                c["status"] = "modified" if sha != e["sha256"] else "unchanged"
            elif c["status"] == "unchanged" and e["sha256"] and sha != e["sha256"]:
                c["status"] = "modified"  # same headers, different bytes
            e["sha256"] = sha
            e["length"] = len(blobs[c["key"]])
        changed = bool(removed) or any(c["status"] in ("added", "modified") for _, c in current)
        if changed:
            dates = [http_date(c["entry"]["last_modified"]) for _, c in current
                     if c["status"] in ("added", "modified")]
            dates = [d for d in dates if d]
            snap = max(dates) if dates else dt.date.today()
            # The build picks the newest folder, so a new snapshot must sort after every
            # existing one, even when its PDFs' Last-Modified dates are older (they often
            # are: hand-made folders are named by w.e.f. or download date).
            existing = [dt.date.fromisoformat(d.name) for d in (snapshot_root / railway).glob("*")
                        if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)]
            if existing and snap <= max(existing):
                snap = max(existing) + dt.timedelta(days=1)
            snapshot_dir = snapshot_root / railway / snap.isoformat()
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            lines = []
            for pid, c in current:
                if c["key"] in blobs:
                    target = snapshot_dir / saved_as[c["key"]]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(blobs[c["key"]])
                    lines.append(f"{saved_as[c['key']]}\t{c['entry']['last_modified']}\t{c['entry']['sha256']}\t{c['url']}")
            (snapshot_dir / "SOURCES.txt").write_text(
                "# file\tLast-Modified\tsha256\turl\n" + "\n".join(sorted(lines)) + "\n")

    rows = [{"page": pid, "status": c["status"], "name": c["name"], "title": c["title"],
             "url": c["url"], "entry": c["entry"], "saved_as": saved_as.get(c["key"])}
            for pid, c in current] + removed

    if changed:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    result = {"railway": railway, "name": cfg["name"], "changed": changed, "errors": errors,
              "notes": notes, "unclassified": unclassified, "conflicts": conflicts,
              "snapshot": str(snapshot_dir.relative_to(ROOT)) if snapshot_dir and snapshot_dir.is_relative_to(ROOT) else (str(snapshot_dir) if snapshot_dir else None),
              "counts": {s: sum(r["status"] == s for r in rows)
                         for s in ("added", "modified", "removed", "unchanged", "failed")}}
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (out / "report.md").write_text(report_md(result, rows, sources[railway]))
    (out / "errors.md").write_text(errors_md(result))
    return result


# ----------------------------------------------------------------------- reports

ICON = {"added": "🆕 added", "modified": "✏️ modified", "removed": "🗑️ removed",
        "unchanged": "unchanged", "failed": "⚠️ download failed"}


def report_md(result: dict, rows: list[dict], cfg: dict) -> str:
    c = result["counts"]
    out = [f"## {result['name']} timetable PDFs changed\n",
           f"Detected by the [timetable watcher](https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'faraazb/rahi')}/blob/main/watch/README.md) on "
           f"{dt.date.today().isoformat()}: **{c['added']} added, {c['modified']} modified, "
           f"{c['removed']} removed**, {c['unchanged']} unchanged.\n"]
    if result["snapshot"]:
        out.append(f"Full snapshot of the current PDFs: `{result['snapshot']}/`\n")
    order = {"added": 0, "modified": 1, "removed": 2, "failed": 3, "unchanged": 4}
    for page in cfg["pages"]:
        prs = sorted([r for r in rows if r["page"] == page["id"]], key=lambda r: (order[r["status"]], r["name"]))
        if not prs:
            continue
        out.append(f"\n### {page['title']} (`{page['id']}`)\n")
        changed = [r for r in prs if r["status"] != "unchanged"]
        same = [r for r in prs if r["status"] == "unchanged"]
        if changed:
            out += _table(changed)
        else:
            out.append("No changes on this page.")
        if same:
            out.append(f"\n<details><summary>{len(same)} unchanged</summary>\n")
            out += _table(same)
            out.append("\n</details>")
    attention = [f"`{n}` matches no rule in `watch/sources.json`, so it was saved to other/ and the "
                 "parser ignores it. If it is a timetable sheet, add a rule." for n in result["unclassified"]]
    attention += result["conflicts"]
    if attention:
        out.append("\n### ⚠️ Needs attention\n" + "\n".join(f"- {a}" for a in attention))
    if result["notes"]:
        out.append("\n### Notes\n" + "\n".join(f"- {n}" for n in result["notes"]))
    if result["errors"]:
        out.append("\n### Errors during this run\n" + "\n".join(f"- {e}" for e in result["errors"]))
    out.append("""
### Review checklist
- [ ] Changes look like a real timetable revision (new w.e.f. date / PTT number), not a re-upload
- [ ] Every timetable PDF was saved as a sheet ("Saved as" column; nothing under Needs attention)
- [ ] The preview build on this branch passed (its summary is posted as a comment below)
- [ ] Merge to accept the new snapshot: merging publishes it (GitHub Release, then Pages)

<sub>This PR is updated in place by the daily watcher. Closing it without merging is fine:
it will be reopened only if the source changes again.</sub>
""")
    return "\n".join(out) + "\n"


def _table(rows: list[dict]) -> list[str]:
    out = ["| Status | Link text | File | Saved as | Last-Modified | Size | sha256 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        e = r["entry"]
        name = f"[{r['name']}]({r['url']})" if r["url"] else r["name"]
        size = f"{e['length'] / 1024:.0f} KiB" if e.get("length") else "?"
        sha = f"`{e['sha256'][:12]}`" if e.get("sha256") else ""
        title = (r["title"] or "").replace("|", "\\|")
        saved = f"`{r['saved_as']}`" if r.get("saved_as") else ""
        out.append(f"| {ICON[r['status']]} | {title} | {name} | {saved} | {e.get('last_modified') or '?'} | {size} | {sha} |")
    return out


def errors_md(result: dict) -> str:
    if not result["errors"]:
        return ""
    return (f"The timetable watcher could not fully check **{result['name']}** on "
            f"{dt.date.today().isoformat()}. The last known good state was kept; nothing was "
            "treated as removed.\n\n"
            + "\n".join(f"- {e}" for e in result["errors"])
            + "\n\nThis issue is updated by each failing run and closed automatically on the "
            "first clean run. If the site moved (new CMS, new URL), update `watch/sources.json`.\n")


# -------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("railway")
    ap.add_argument("--sources", type=pathlib.Path, default=ROOT / "watch/sources.json")
    ap.add_argument("--state-dir", type=pathlib.Path, default=ROOT / "watch/state")
    ap.add_argument("--snapshot-root", type=pathlib.Path, default=ROOT / "data/raw")
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--forget", default="",
                    help="testing: comma-separated substrings of file paths to treat as never seen ('*' = all)")
    a = ap.parse_args()
    sources = json.loads(a.sources.read_text())
    if a.railway not in sources:
        ap.error(f"unknown railway {a.railway!r}; known: {', '.join(sources)}")
    forget = [f.strip() for f in a.forget.split(",") if f.strip()]
    r = run(a.railway, sources, a.state_dir / f"{a.railway}.json", a.snapshot_root, a.out, forget)
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
