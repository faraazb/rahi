"""Package a built timetable database as a release the app can download.

    <out>/<tag>/manifest.json
    <out>/<tag>/mumbai-local.sqlite.gz

The manifest sits next to the database and names it by a relative URL, so the
same files work wherever they are hosted: a GitHub Release
(releases/download/<tag>/...), GitHub Pages, or the local mock server. The
app fetches the manifest, compares `version`, downloads `db.url` resolved
against the manifest's own URL, and checks `db.sha256` before using it.

Why not let the browser read GitHub Release assets directly? Their downloads
redirect to a storage host that sends no CORS header, so a page on GitHub
Pages cannot fetch them (checked 2026-11-05). Publishing the same release
directory to Pages, next to the app, avoids that; the Release stays the
versioned archive.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_ASSET = "mumbai-local.sqlite.gz"

# Tables built from sources we may not redistribute yet (see platforms.py, rakes.py).
# A database carrying one is released only when the release is marked local, or
# when the caller passes merge_layers (the repository's MERGE_YATRI_PLATFORMS switch
# in CI), so it can never reach a public GitHub Release by accident.
LOCAL_ONLY_TABLES = ("platform", "rake_next")


class LocalOnlyData(Exception):
    pass


# meta rows that record when a build ran rather than what it holds.
VOLATILE_META = ("built_at", "platforms_fetched_at")
_VOLATILE_ROWS = tuple(f"INSERT INTO \"meta\" VALUES('{key}'," for key in VOLATILE_META)


def data_sha256(db: sqlite3.Connection) -> str:
    """Hash of the database's content without its build and fetch times, so
    rebuilding the same sources gives the same value and publishing can skip
    unchanged data."""
    h = hashlib.sha256()
    for line in db.iterdump():
        if not line.startswith(_VOLATILE_ROWS):
            h.update(line.encode())
            h.update(b"\n")
    return h.hexdigest()


def data_sha256_of_file(path: Path) -> str:
    """data_sha256 of a database file, gzipped (a release asset) or not."""
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    db = sqlite3.connect(":memory:")
    db.deserialize(raw)
    try:
        return data_sha256(db)
    finally:
        db.close()


def _effective_from(meta: dict[str, str], line: str) -> str | None:
    """The line's w.e.f. date, recorded at build time (see editions.py). Databases
    built before that fall back to the WR convention: folder named by its w.e.f."""
    key = f"{line.lower()}_effective_from"
    if key in meta:
        return meta[key] or None
    src = meta.get(f"{line.lower()}_source_dir")
    return Path(src).name if src else None


def _line_sources(meta: dict[str, str], line: str) -> dict[str, str]:
    """The line's own source files and their sha256 (<line>_files picks them out of the
    per-railway <railway>_sources); older databases only have the per-railway lists."""
    files = meta.get(f"{line.lower()}_files")
    if files is None:
        return json.loads(meta.get(f"{line.lower()}_sources", "{}"))
    every: dict[str, str] = {}
    for key, value in meta.items():
        if key.endswith("_sources"):
            every |= json.loads(value)
    return {f: every.get(f, "") for f in json.loads(files)}


def make_release(db_path: Path, out_dir: Path, tag: str | None = None, local: bool = False,
                 merge_layers: bool = False) -> Path:
    raw = db_path.read_bytes()
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    meta = dict(db.execute("SELECT key, value FROM meta"))
    tables = {n for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    local_layers = [t for t in LOCAL_ONLY_TABLES if t in tables]
    if local_layers and not (local or merge_layers):
        db.close()
        raise LocalOnlyData(
            f"{db_path} carries local-only data ({', '.join(local_layers)}); "
            "rebuild without it, pass --local for a release that stays on this machine, "
            "or --merge-layers once publishing it is approved")
    lines = [
        {"code": code, "name": name, "effective_from": _effective_from(meta, code),
         "as_of": meta.get(f"{code.lower()}_as_of") or None,
         "sources": _line_sources(meta, code)}
        for code, name in db.execute("SELECT code, name FROM line ORDER BY id")
    ]
    counts = {
        "trains": db.execute("SELECT COUNT(*) FROM train").fetchone()[0],
        "stations": db.execute("SELECT COUNT(*) FROM line_station").fetchone()[0],
    }
    content = data_sha256(db)
    db.close()

    content_hash = hashlib.sha256(raw).hexdigest()
    now = datetime.now(timezone.utc)
    tag = tag or f"data-{now:%Y%m%d}-{content_hash[:8]}"
    # mtime=0 keeps the gzip byte-identical for identical databases.
    packed = gzip.compress(raw, compresslevel=9, mtime=0)

    rel = out_dir / tag
    rel.mkdir(parents=True, exist_ok=True)
    (rel / DB_ASSET).write_bytes(packed)
    manifest = {
        "format": 1,
        "version": tag,
        "schema_version": int(meta["schema_version"]),
        "published_at": now.isoformat(timespec="seconds"),
        "built_at": meta.get("built_at"),
        "lines": lines,
        "counts": counts,
        # Optional layers inside the database; the app checks for the tables itself.
        # local_only stays true unless the layers were explicitly approved for merging.
        "layers": {t: {"source": meta.get("platforms_source"), "local_only": not merge_layers}
                   for t in local_layers},
        "local": local,
        "db": {
            "url": DB_ASSET,
            "encoding": "gzip",
            "size": len(packed),
            "sha256": hashlib.sha256(packed).hexdigest(),
            "raw_size": len(raw),
            "raw_sha256": content_hash,
        },
        # Same data gives the same value whenever it was built (raw_sha256 changes with built_at).
        "data_sha256": content,
    }
    (rel / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return rel


if __name__ == "__main__":
    # python -m mumbailocal.release data-sha256 <db.sqlite[.gz]>
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "data-sha256":
        sys.exit("usage: python -m mumbailocal.release data-sha256 <db.sqlite[.gz]>")
    print(data_sha256_of_file(Path(sys.argv[2])))
