"""The release the app downloads: layout, checksums, manifest fields."""

import gzip
import hashlib
import json
import sqlite3

import pytest

from mumbailocal import build_db
from mumbailocal.model import Diagnostics
from mumbailocal.paths import RAW_DIR
from mumbailocal.release import DB_ASSET, make_release
from mumbailocal.sources import wr


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    src = RAW_DIR / "wr" / "2026-09-01"
    if not src.exists():
        pytest.skip("WR 2026 fixture PDFs not present")
    path = tmp_path_factory.mktemp("db") / "mumbai-local.sqlite"
    trains = wr.parse_dir(src, Diagnostics())
    build_db.build(path, {"WR": trains}, {"wr_source_dir": str(src), "wr_sources": json.dumps({"dn.pdf": "x"})})
    return path


def test_release_layout_and_checksums(db_path, tmp_path):
    rel = make_release(db_path, tmp_path, tag="data-test")
    assert rel == tmp_path / "data-test"
    m = json.loads((rel / "manifest.json").read_text())
    packed = (rel / DB_ASSET).read_bytes()
    raw = gzip.decompress(packed)

    # The app resolves db.url against the manifest's own URL, so it must be a
    # bare file name next to the manifest.
    assert m["db"]["url"] == DB_ASSET and "/" not in m["db"]["url"]
    assert m["db"]["sha256"] == hashlib.sha256(packed).hexdigest()
    assert m["db"]["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert (m["db"]["size"], m["db"]["raw_size"]) == (len(packed), len(raw))
    assert raw == db_path.read_bytes()

    assert m["format"] == 1 and m["version"] == "data-test"
    assert m["schema_version"] == build_db.SCHEMA_VERSION
    assert m["lines"][0]["code"] == "WR" and m["lines"][0]["effective_from"] == "2026-09-01"
    assert m["counts"]["trains"] == 1406


def test_identical_database_gives_identical_bytes(db_path, tmp_path):
    a = make_release(db_path, tmp_path / "a", tag="t")
    b = make_release(db_path, tmp_path / "b", tag="t")
    assert (a / DB_ASSET).read_bytes() == (b / DB_ASSET).read_bytes()


def test_default_tag_names_content(db_path, tmp_path):
    rel = make_release(db_path, tmp_path)
    content = hashlib.sha256(db_path.read_bytes()).hexdigest()[:8]
    assert rel.name.startswith("data-") and rel.name.endswith(content)
    sqlite3.connect(f"file:{db_path}?mode=ro", uri=True).execute("SELECT 1 FROM meta").fetchone()
