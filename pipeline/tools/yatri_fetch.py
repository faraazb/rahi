#!/usr/bin/env python3
"""Fetch the Yatri app from Google Play and extract its bundled database.

LOCAL ONLY: the database is used for the local platforms layer and as a
validation reference. Nothing fetched here is committed or published.

    yatri_fetch.py                      log in, download if Play has a new version, extract
    yatri_fetch.py --apk path/base.apk  extract from an APK you already have (no network)
    yatri_fetch.py --check              only print the version on Play

Steps:
  1. Log in to Google Play, one of two ways:
       - your own account: GOOGLE_EMAIL + GOOGLE_AAS_TOKEN (see apkeep's
         USAGE-google-play.md for getting an AAS token once);
       - a token dispenser, as Aurora Store does: POST the device profile to
         DISPENSER_URL and get back {email, authToken}. Aurora's dispenser
         (https://auroraoss.com/api/auth) only answers clients that identify
         as Aurora Store, so DISPENSER_USER_AGENT must be set to use it.
     Dispensed tokens are cached for TOKEN_TTL in the cache directory.
  2. `apkeep -l` asks Play for the current version; if that version is
     already cached, nothing is downloaded.
  3. `apkeep` downloads the split APKs; only base.apk holds the database.
  4. assets/databases/yatri.db is pulled out with zipfile, checked to be a
     SQLite file with the tables we use, and installed as <cache>/yatri.db
     (the previous copy is kept as yatri.prev.db) with yatri.json beside it.

apkeep (EFF) is pinned in mise.toml. Its device profiles come from the
rs-google-play repository and are downloaded at run time (GPL-3.0; not
vendored here).

Exit status: 0 ok (or nothing new), 1 error, 3 login failed (dispenser down or
rate-limited, bad account token).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = "com.yatrirailways.yatri"
DB_ENTRY = "assets/databases/yatri.db"
REQUIRED_TABLES = {"local_stations", "local_trains", "local_train_schedule"}
DEVICE = "px_9a"
# Pinned to a commit so the profile sent to the dispenser stays the one apkeep 1.1.0 uses.
DEVICE_PROPERTIES_URL = (
    "https://raw.githubusercontent.com/EFForg/rs-google-play/eb423a3edfc653a1d533d4b7f6c9148d5bc144a8/gpapi/device.properties")
TOKEN_TTL = 45 * 60  # dispensed OAuth tokens live about an hour
REPO = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = REPO / "temp.fignore" / "yatri"


class LoginFailed(Exception):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- login

def device_properties(cache: Path) -> dict[str, str]:
    path = cache / "device.properties"
    if not path.exists():
        log(f"downloading device profiles from {DEVICE_PROPERTIES_URL}")
        with urllib.request.urlopen(DEVICE_PROPERTIES_URL, timeout=60) as r:
            path.write_bytes(r.read())
    props, section = {}, None
    for line in path.read_text().splitlines():
        if m := re.match(r"\[(.+)\]", line):
            section = m.group(1)
        elif section == DEVICE and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            props[k] = v.replace("\\:", ":")
    if not props:
        raise SystemExit(f"device profile {DEVICE} not found in {path}")
    return props


def dispensed_login(cache: Path, url: str, user_agent: str, attempts: int) -> tuple[str, str]:
    token_file = cache / "token.json"
    try:
        t = json.loads(token_file.read_text())
        if time.time() - t["at"] < TOKEN_TTL and t.get("url") == url:
            log(f"using cached dispenser token for {t['email']}")
            return t["email"], t["authToken"]
    except (OSError, ValueError, KeyError):
        pass
    body = json.dumps(device_properties(cache)).encode()
    wait = 30
    for i in range(1, attempts + 1):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json", "User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                auth = json.loads(r.read())
            email, token = auth["email"], auth["authToken"]
            token_file.write_text(json.dumps({"email": email, "authToken": token, "at": time.time(), "url": url}))
            token_file.chmod(0o600)
            log(f"dispenser login ok ({email})")
            return email, token
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise LoginFailed(f"dispenser refused this client (HTTP 403); check DISPENSER_USER_AGENT") from e
            reason = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            reason = str(e)
        if i == attempts:
            raise LoginFailed(f"dispenser login failed after {attempts} attempts ({reason})")
        log(f"dispenser: {reason}; retrying in {wait}s ({i}/{attempts})")
        time.sleep(wait)
        wait *= 3
    raise AssertionError


def login(cache: Path, attempts: int) -> list[str]:
    """apkeep arguments that authenticate to Google Play."""
    email, aas = os.environ.get("GOOGLE_EMAIL"), os.environ.get("GOOGLE_AAS_TOKEN")
    if email and aas:
        log(f"using your Google account {email}")
        return ["-e", email, "-t", aas]
    url = os.environ.get("DISPENSER_URL")
    ua = os.environ.get("DISPENSER_USER_AGENT")
    if url and ua:
        email, token = dispensed_login(cache, url, ua, attempts)
        return ["-e", email, "--auth-token", token]
    raise LoginFailed(
        "no Google Play login configured: set GOOGLE_EMAIL and GOOGLE_AAS_TOKEN, "
        "or DISPENSER_URL and DISPENSER_USER_AGENT")


# ---------------------------------------------------------------- download

def apkeep(args: list[str]) -> subprocess.CompletedProcess:
    exe = shutil.which("apkeep")
    if not exe:
        raise SystemExit("apkeep not found: run `mise install` (it is pinned in mise.toml)")
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=1800)


def play_version(auth: list[str]) -> str:
    r = apkeep(["-l", "-a", PACKAGE, "-d", "google-play", *auth, "-o", f"device={DEVICE}"])
    out = r.stdout + r.stderr
    if r.returncode != 0:
        raise LoginFailed(f"apkeep could not list versions: {out.strip()[-500:]}")
    versions = re.findall(r"\b\d+(?:\.\d+)+\b", out)
    if not versions:
        raise SystemExit(f"could not read a version from apkeep's output:\n{out}")
    return versions[-1]


def download(auth: list[str], version: str, dest: Path) -> Path:
    """Download into dest/; return the APK that contains the database."""
    dest.mkdir(parents=True, exist_ok=True)
    r = apkeep(["-a", f"{PACKAGE}@{version}", "-d", "google-play", *auth, "--accept-tos",
                "-o", f"device={DEVICE},split_apk=true", str(dest)])
    if r.returncode != 0:
        raise SystemExit(f"apkeep download failed:\n{(r.stdout + r.stderr).strip()[-1500:]}")
    apk = find_db_apk(dest)
    if not apk:
        raise SystemExit(f"downloaded files in {dest} hold no {DB_ENTRY}")
    return apk


def find_db_apk(root: Path) -> Path | None:
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in (".apk", ".xapk", ".zip") and zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                if DB_ENTRY in z.namelist():
                    return p
    return None


# ---------------------------------------------------------------- extract

def extract(apk: Path, cache: Path, version: str | None) -> dict:
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        out = Path(tmp) / "yatri.db"
        with zipfile.ZipFile(apk) as z, z.open(DB_ENTRY) as src, out.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        data = out.read_bytes()
        if not data.startswith(b"SQLite format 3\0"):
            raise SystemExit(f"{DB_ENTRY} in {apk} is not a SQLite database")
        db = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
        tables = {n for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise SystemExit(f"Yatri's database no longer has {sorted(missing)}; the schema changed")
        updated = db.execute("SELECT MAX(updated_at) FROM local_train_schedule").fetchone()[0]
        rows = db.execute("SELECT COUNT(*) FROM local_train_schedule").fetchone()[0]
        db.close()
        info = {
            "package": PACKAGE,
            "version": version,
            "apk": str(apk.relative_to(REPO)) if apk.is_relative_to(REPO) else str(apk),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "schedule_rows": rows,
            "data_updated_at": updated,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        target, meta = cache / "yatri.db", cache / "yatri.json"
        old = json.loads(meta.read_text()) if meta.exists() else None
        if old and old.get("sha256") == info["sha256"]:
            log(f"yatri.db unchanged (sha256 {info['sha256'][:12]})")
            return info
        if target.exists():
            target.replace(cache / "yatri.prev.db")
            if meta.exists():
                meta.replace(cache / "yatri.prev.json")
        out.replace(target)
        meta.write_text(json.dumps(info, indent=1))
    log(f"extracted {target} ({info['size']:,} bytes, {rows:,} stop rows, data updated {updated})")
    return info


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help=f"default: {DEFAULT_CACHE.relative_to(REPO)}")
    ap.add_argument("--apk", type=Path, help="extract from this APK instead of downloading")
    ap.add_argument("--check", action="store_true", help="only print the version on Google Play")
    ap.add_argument("--force", action="store_true", help="download even if this version is cached")
    ap.add_argument("--attempts", type=int, default=3, help="dispenser login attempts (backoff 30s, 90s, ...)")
    a = ap.parse_args()
    cache = a.cache
    cache.mkdir(parents=True, exist_ok=True)

    if a.apk:
        extract(a.apk, cache, version=None)
        return 0
    try:
        auth = login(cache, a.attempts)
        version = play_version(auth)
    except LoginFailed as e:
        log(f"login failed: {e}")
        return 3
    log(f"Google Play has {PACKAGE} {version}")
    if a.check:
        return 0
    apk_dir = cache / "apk" / version
    apk = None if a.force else find_db_apk(apk_dir) if apk_dir.exists() else None
    if apk:
        log(f"version {version} already downloaded: {apk}")
    else:
        if apk_dir.exists():
            shutil.rmtree(apk_dir)
        log(f"downloading {PACKAGE} {version} ...")
        apk = download(auth, version, apk_dir)
        # Keep only the newest download; each is ~130 MB.
        for old in (cache / "apk").iterdir():
            if old != apk_dir and old.is_dir():
                shutil.rmtree(old)
    extract(apk, cache, version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
