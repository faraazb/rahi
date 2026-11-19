"""Which releases GitHub Pages serves, and the pointers the app reads."""

import json

import pytest

from mumbailocal import pages_data
from mumbailocal.release import DB_ASSET


def write(releases, tag, published, schema, local=False):
    d = releases / tag
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({
        "version": tag, "published_at": published, "schema_version": schema, "local": local,
        "lines": [{"code": "WR", "name": "Western", "effective_from": "2026-09-01", "as_of": None}],
        "counts": {"trains": 1}, "db": {"url": DB_ASSET, "sha256": tag}}))
    (d / DB_ASSET).write_bytes(tag.encode())


@pytest.fixture
def releases(tmp_path):
    r = tmp_path / "rel"
    write(r, "v1", "2026-01-01T00:00:00+00:00", 2)
    write(r, "v2", "2026-02-01T00:00:00+00:00", 2)
    write(r, "v3", "2026-03-01T00:00:00+00:00", 3)
    write(r, "v4", "2026-04-01T00:00:00+00:00", 3)
    write(r, "local", "2026-05-01T00:00:00+00:00", 3, local=True)
    return r


def test_serves_latest_previous_and_newest_per_schema(releases):
    assert pages_data.serve(pages_data.load(releases), "v4") == {
        "latest": "v4", "previous": "v3", "schema-2": "v2", "schema-3": "v4"}


def test_rollback_points_everything_at_the_chosen_release(releases):
    assert pages_data.serve(pages_data.load(releases), "v3") == {
        "latest": "v3", "previous": "v2", "schema-2": "v2", "schema-3": "v3"}


def test_build_writes_versioned_folders_pointers_and_index(releases, tmp_path):
    out = tmp_path / "site" / "data"
    index = pages_data.build(releases, out, "v4", "faraazb/rahi")
    assert sorted(p.name for p in out.iterdir()) == ["index.json", "latest", "schema-2", "schema-3", "v2", "v3", "v4"]
    latest = json.loads((out / "latest" / "manifest.json").read_text())
    assert latest["version"] == "v4" and latest["db"]["url"] == f"../v4/{DB_ASSET}"
    assert json.loads((out / "v4" / "manifest.json").read_text())["db"]["url"] == DB_ASSET  # unchanged
    assert (out / "v2" / DB_ASSET).read_bytes() == b"v2"
    assert [v["version"] for v in index["versions"]] == ["v4", "v3", "v2", "v1"]  # local build left out
    assert [v["on_pages"] for v in index["versions"]] == [True, True, True, False]
    assert index["versions"][3]["release"] == "https://github.com/faraazb/rahi/releases/tag/v1"
    assert "previous" not in index["pointers"]


def test_build_refuses_a_served_release_without_its_database(releases, tmp_path):
    (releases / "v2" / DB_ASSET).unlink()
    with pytest.raises(SystemExit):
        pages_data.build(releases, tmp_path / "data", "v4", "faraazb/rahi")
