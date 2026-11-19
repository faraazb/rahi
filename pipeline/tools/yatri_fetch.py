#!/usr/bin/env python3
"""Fetch the Yatri app from Google Play and extract its bundled database.

LOCAL ONLY: the database is used for the local platforms layer and as a
validation reference. Nothing fetched here is committed or published.

    yatri_fetch.py                      log in, download the current version, extract
    yatri_fetch.py --apk path/base.apk  extract from an APK you already have (no network)

Steps:
  1. Log in to Google Play, one of two ways:
       - your own account: GOOGLE_EMAIL + GOOGLE_AAS_TOKEN (see apkeep's
         USAGE-google-play.md for getting an AAS token once);
       - a token dispenser, as Aurora Store does: POST the device profile to
         DISPENSER_URL and get back {email, authToken}. Aurora's dispenser
         (https://auroraoss.com/api/auth) only answers clients that identify
         as Aurora Store, so DISPENSER_USER_AGENT must be set to use it.
     Dispensed tokens are cached for TOKEN_TTL in the cache directory.
  2. `apkeep` downloads the current split APKs; only base.apk holds the
     database. Google Play serves only the current version and apkeep cannot
     ask which one that is (`apkeep -l` prints no versions for Play, and
     `app@version` is refused), so the version is read afterwards from
     base.apk's AndroidManifest.xml.
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
import struct
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
                raise LoginFailed(
                    "dispenser refused this client (HTTP 403): a wrong DISPENSER_USER_AGENT, or the "
                    "dispenser blocks this IP (Aurora's blocks GitHub's runners)") from e
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
    # Pasted secrets often carry a trailing newline or quotes; either makes the dispenser refuse.
    url = (os.environ.get("DISPENSER_URL") or "").strip().strip("'\"")
    ua = (os.environ.get("DISPENSER_USER_AGENT") or "").strip().strip("'\"")
    if url and ua:
        shape = "looks like <package>-<version>-<code>" if re.fullmatch(r"[\w.]+-[\w.]+-\d+", ua) \
            else "does NOT look like <package>-<version>-<code>"
        log(f"dispenser login: user agent of {len(ua)} characters, {shape}")
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


def download(auth: list[str], dest: Path) -> Path:
    """Download the current version into dest/; return the APK that contains the database."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    r = apkeep(["-a", PACKAGE, "-d", "google-play", *auth, "--accept-tos",
                "-o", f"device={DEVICE},split_apk=true", str(dest)])
    out = (r.stdout + r.stderr).strip()
    if "Could not log in" in out:
        raise LoginFailed(out[-500:])
    apk = find_db_apk(dest)
    if r.returncode != 0 or not apk:
        # apkeep reports most failures as "... Skipping..." and still exits 0.
        hint = (" Play did not offer the app to this account and device: it may need the app"
                " installed once from India on this account, or a different device profile."
                if "Invalid app response" in out else "")
        raise SystemExit(f"apkeep download gave no {DB_ENTRY}.{hint}\n{out[-1500:]}")
    return apk


def manifest_version(apk: Path) -> tuple[str | None, int | None]:
    """versionName and versionCode from an APK's binary AndroidManifest.xml."""
    with zipfile.ZipFile(apk) as z:
        data = z.read("AndroidManifest.xml")
    strings: list[str] = []
    pos = 8  # after the XML chunk header
    while pos + 8 <= len(data):
        ctype, hsize, csize = struct.unpack_from("<HHI", data, pos)
        if ctype == 0x0001:  # string pool
            count, _, flags, start = struct.unpack_from("<IIII", data, pos + 8)
            for i in range(count):
                off = pos + start + struct.unpack_from("<I", data, pos + hsize + 4 * i)[0]
                if flags & 0x100:  # UTF-8: char count, then byte count, each 1 or 2 bytes
                    off += 2 if data[off] & 0x80 else 1
                    n = data[off]
                    off += 1
                    if n & 0x80:
                        n = ((n & 0x7F) << 8) | data[off]
                        off += 1
                    strings.append(data[off:off + n].decode("utf-8", "replace"))
                else:  # UTF-16: unit count in 1 or 2 u16s
                    n = struct.unpack_from("<H", data, off)[0]
                    off += 2
                    if n & 0x8000:
                        n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", data, off)[0]
                        off += 2
                    strings.append(data[off:off + 2 * n].decode("utf-16-le", "replace"))
        elif ctype == 0x0102 and strings[struct.unpack_from("<I", data, pos + 20)[0]] == "manifest":
            astart, asize, acount = struct.unpack_from("<HHH", data, pos + 24)
            found: dict = {}
            for i in range(acount):
                _, name, raw, _, _, vtype, value = struct.unpack_from("<IIIHBBI", data, pos + 16 + astart + i * asize)
                if strings[name] in ("versionName", "versionCode"):
                    found[strings[name]] = strings[raw] if raw != 0xFFFFFFFF else value if vtype in (0x10, 0x11) else None
            return found.get("versionName"), found.get("versionCode")
        pos += csize
    return None, None


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
    ap.add_argument("--attempts", type=int, default=3, help="dispenser login attempts (backoff 30s, 90s, ...)")
    a = ap.parse_args()
    cache = a.cache
    cache.mkdir(parents=True, exist_ok=True)

    if a.apk:
        name, code = manifest_version(a.apk)
        extract(a.apk, cache, version=f"{name} ({code})" if name else None)
        return 0
    try:
        auth = login(cache, a.attempts)
        log(f"downloading the current {PACKAGE} from Google Play ...")
        apk = download(auth, cache / "apk" / "current")
    except LoginFailed as e:
        log(f"login failed: {e}")
        return 3
    name, code = manifest_version(apk)
    version = f"{name} ({code})" if name else None
    log(f"downloaded {PACKAGE} {version or '(version unknown)'}")
    extract(apk, cache, version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
