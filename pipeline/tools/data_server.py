#!/usr/bin/env python3
"""Local stand-in for the GitHub Releases that will carry the timetable.

Serves pipeline/build/releases/<tag>/ with GitHub's URL shapes:

  GET /<owner>/<repo>/releases/latest/download/<asset>
      302 -> /<owner>/<repo>/releases/download/<latest tag>/<asset>
  GET /<owner>/<repo>/releases/download/<tag>/<asset>
      the file

The latest tag is the one whose manifest has the newest published_at, so
`mise run release` followed by an app refresh exercises the update path.

Unlike GitHub it sends `Access-Control-Allow-Origin: *`. Real release
downloads carry no CORS header, so production serves the same release folder
from GitHub Pages next to the app (see mumbailocal/release.py).

Usage: data_server.py [--dir pipeline/build/releases] [--port 8787] [--delay 0.5]
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROUTE = re.compile(r"^/([\w.-]+)/([\w.-]+)/releases/(latest/download|download/([\w.-]+))/([\w.-]+)$")


def latest_tag(root: Path) -> str | None:
    best = None
    for manifest in root.glob("*/manifest.json"):
        published = json.loads(manifest.read_text()).get("published_at", "")
        if best is None or published > best[0]:
            best = (published, manifest.parent.name)
    return best[1] if best else None


def make_handler(root: Path, delay: float):
    class Handler(BaseHTTPRequestHandler):
        def _headers(self, status: int, extra: dict[str, str]) -> None:
            self.send_response(status)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Expose-Headers", "Content-Length")
            for k, v in extra.items():
                self.send_header(k, v)
            self.end_headers()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._headers(204, {"Access-Control-Allow-Methods": "GET, HEAD", "Access-Control-Max-Age": "600"})

        def do_HEAD(self) -> None:  # noqa: N802
            self.do_GET(body=False)

        def do_GET(self, body: bool = True) -> None:  # noqa: N802
            if delay:
                time.sleep(delay)
            m = ROUTE.match(self.path.split("?")[0])
            if not m:
                return self._headers(404, {"Content-Length": "0"})
            owner, repo, kind, tag, asset = m.groups()
            if kind == "latest/download":
                tag = latest_tag(root)
                if tag is None:
                    return self._headers(404, {"Content-Length": "0"})
                # Relative, so it also works behind a path-prefixing proxy
                # (the app's dev server forwards /data/* here).
                return self._headers(302, {
                    "Location": f"../../download/{tag}/{asset}",
                    "Cache-Control": "no-store", "Content-Length": "0"})
            path = root / tag / asset
            if not path.is_file() or root not in path.resolve().parents:
                return self._headers(404, {"Content-Length": "0"})
            data = path.read_bytes()
            ctype = "application/json" if asset.endswith(".json") else (
                mimetypes.guess_type(asset)[0] or "application/octet-stream")
            if asset.endswith(".gz"):
                ctype = "application/gzip"  # served as-is; the app decompresses
            self._headers(200, {"Content-Type": ctype, "Content-Length": str(len(data)),
                                "Cache-Control": "public, max-age=31536000, immutable"})
            if body:
                self.wfile.write(data)

        def log_message(self, fmt: str, *args) -> None:
            print(f"[data] {self.address_string()} {fmt % args}")

    return Handler


def main() -> None:
    here = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(here / "build" / "releases"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--delay", type=float, default=0.0, help="seconds added to every response")
    a = ap.parse_args()
    root = Path(a.dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    print(f"serving releases from {root} (latest: {latest_tag(root)})")
    print(f"manifest: http://{a.host}:{a.port}/faraazb/rahi/releases/latest/download/manifest.json")
    ThreadingHTTPServer((a.host, a.port), make_handler(root, a.delay)).serve_forever()


if __name__ == "__main__":
    main()
