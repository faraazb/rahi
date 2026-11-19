"""Lay out the timetable releases for GitHub Pages.

GitHub Pages keeps nothing between deploys, so every deploy rebuilds data/ from
the GitHub Releases (the archive):

    data/<tag>/manifest.json            a release, unchanged; db.url is relative
    data/<tag>/mumbai-local.sqlite.gz
    data/latest/manifest.json           pointer: the latest release's manifest with
                                        db.url = "../<tag>/mumbai-local.sqlite.gz"
    data/schema-<n>/manifest.json       pointer to the newest release of schema n
    data/index.json                     every release, and which ones are on Pages

Versioned folders never change, so the CDN cannot pair a new manifest with an
old database. Only some releases are served (`serve`):
  - the latest one (GitHub's "latest" flag, so marking an older release latest
    and redeploying rolls the app back);
  - the one published just before it, so an update that read the previous
    manifest moments before a deploy still finds its database;
  - the newest one of every schema version, so app builds that only read an
    older schema keep getting updates of it (they read data/schema-<n>/).
Older ones stay in GitHub Releases and are listed in index.json.

    python -m mumbailocal.pages_data serve  <releases-dir> --latest <tag>
    python -m mumbailocal.pages_data build  <releases-dir> <out-data-dir> --latest <tag> --repo <owner/name>

<releases-dir>/<tag>/ holds each release's manifest.json, and for the served ones
also its database.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .release import DB_ASSET


def load(releases: Path) -> dict[str, dict]:
    out = {}
    for m in sorted(releases.glob("*/manifest.json")):
        manifest = json.loads(m.read_text())
        if not manifest.get("local"):  # never serve a local-only build
            out[m.parent.name] = manifest
    return out


def by_date(manifests: dict[str, dict]) -> list[str]:
    return sorted(manifests, key=lambda t: (manifests[t].get("published_at") or "", t))


def serve(manifests: dict[str, dict], latest: str) -> dict[str, str]:
    """{pointer name: tag} for every pointer; the served tags are its values plus 'previous'."""
    if latest not in manifests:
        raise SystemExit(f"latest release {latest} has no manifest")
    order = by_date(manifests)
    pointers = {"latest": latest}
    i = order.index(latest)
    if i > 0:
        pointers["previous"] = order[i - 1]
    newest: dict[int, str] = {}
    for tag in order:
        newest[manifests[tag]["schema_version"]] = tag
    newest[manifests[latest]["schema_version"]] = latest  # a rollback wins over newer releases
    for schema, tag in sorted(newest.items()):
        pointers[f"schema-{schema}"] = tag
    return pointers


def build(releases: Path, out: Path, latest: str, repo: str) -> dict:
    manifests = load(releases)
    pointers = serve(manifests, latest)
    served = sorted(set(pointers.values()))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for tag in served:
        src = releases / tag
        if not (src / DB_ASSET).exists():
            raise SystemExit(f"{tag} is served but its database was not downloaded")
        (out / tag).mkdir()
        shutil.copy(src / "manifest.json", out / tag / "manifest.json")
        shutil.copy(src / DB_ASSET, out / tag / DB_ASSET)
    for name, tag in pointers.items():
        if name == "previous":
            continue  # served for in-flight downloads only; nothing points at it
        m = dict(manifests[tag])
        m["db"] = {**m["db"], "url": f"../{tag}/{m['db']['url']}"}
        (out / name).mkdir()
        (out / name / "manifest.json").write_text(json.dumps(m, indent=1))
    index = {
        "latest": latest,
        "pointers": {k: v for k, v in pointers.items() if k != "previous"},
        "versions": [
            {"version": tag,
             "published_at": manifests[tag].get("published_at"),
             "schema_version": manifests[tag]["schema_version"],
             "counts": manifests[tag].get("counts"),
             "data_sha256": manifests[tag].get("data_sha256"),
             "lines": [{k: line.get(k) for k in ("code", "name", "effective_from", "as_of")}
                       for line in manifests[tag].get("lines", [])],
             "on_pages": tag in served,
             "release": f"https://github.com/{repo}/releases/tag/{tag}"}
            for tag in reversed(by_date(manifests))
        ],
    }
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="print the tags whose databases must be downloaded")
    s.add_argument("releases", type=Path)
    s.add_argument("--latest", required=True)
    b = sub.add_parser("build", help="write the data/ folder")
    b.add_argument("releases", type=Path)
    b.add_argument("out", type=Path)
    b.add_argument("--latest", required=True)
    b.add_argument("--repo", required=True)
    a = ap.parse_args()
    if a.cmd == "serve":
        print("\n".join(sorted(set(serve(load(a.releases), a.latest).values()))))
    else:
        index = build(a.releases, a.out, a.latest, a.repo)
        print(json.dumps(index["pointers"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
