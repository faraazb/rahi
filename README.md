# Mumbai local timetable

An open-source, ad-free Mumbai suburban train timetable. Built only from official sources: the
Western and Central Railway timetable PDFs, plus NTES for the Panvel–Vasai and Neral–Matheran
trains (not built yet).

Lines parsed: Western (`WR`), Central Main with the Karjat/Khopoli and Kasara branches (`CR`),
Harbour (`HR`), Trans-Harbour (`THR`), Port/Uran (`UR`) and Pune–Lonavala (`PUNE`).
`mise run compare -- --line CR` checks one line against the local Yatri reference DB; the
results are in `docs/observations.md`.

## Layout

```
app/            SvelteKit + Vite PWA (TypeScript), served from GitHub Pages
pipeline/       Python: PDF parsers -> SQLite timetable, release gate, tests
  src/mumbailocal/   grid engine (pdfgrid), per-source adapters (sources/wr.py, sources/cr.py, sources/ntes.py), NTES client (ntes.py), DB builder
  tests/             golden tests and the all-releases regression suite
  tools/             dev tools: testbench UI, NTES fetcher, Yatri fetch + comparison
  build/             generated databases (not committed)
data/           inputs shared by pipeline and app
  raw/<line>/<date>/ official timetable PDFs, one folder per release
  stations/          curated station tables per line (codes, aliases, branch graph)
  ref/               reference lists (NTES station codes)
docs/           research (OVERVIEW.md) and source discrepancies (observations.md)
temp.fignore/   local-only, never committed: APKs, decompiled sources, reference DBs, tools
```

## Tooling

Tools are pinned in `mise.toml` (Python 3.13, uv, Node 26 LTS). From the repo root:

```sh
mise install                                   # once
mise run test                                  # pipeline tests
mise run ntes-fetch -- data/raw/ntes/<date>   # save NTES pages (Vasai–Diva–Panvel MEMUs, Matheran)
mise run build -- --wr data/raw/wr/2026-09-01 --cr data/raw/cr/2026-11-01 --ntes data/raw/ntes/2026-11-07   # all lines, gated
mise run wr -- data/raw/wr/2026-09-01          # WR only (mise run cr -- data/raw/cr/<date>: CR only)
mise run release                               # package it as pipeline/build/releases/<tag>/
mise run testbench                             # browse the parsed DB at http://127.0.0.1:8000
```

## Platforms (from Yatri, off by default)

No official source publishes platform numbers. Local builds can add them from the database bundled
in the Yatri app; releases carry them only when `MERGE_YATRI_PLATFORMS` is turned on, which waits
until redistribution is agreed.

```sh
mise run yatri -- --apk temp.fignore/apks/yatri/base.apk   # extract from an APK you have, or
mise run yatri                                  # fetch from Google Play (needs a login, see below)
mise run wr -- data/raw/wr/2026-09-01           # rebuilds the DB without platforms
mise run platforms                              # match platforms + door sides in, gated on coverage
mise run release-local                          # `mise run release` refuses a DB with platforms
```

`pipeline/tools/yatri_fetch.py` logs in to Google Play with your own account (`GOOGLE_EMAIL` and
`GOOGLE_AAS_TOKEN`) or a token dispenser (`DISPENSER_URL` and `DISPENSER_USER_AGENT`). It downloads
the current version with apkeep (pinned in `mise.toml`), and extracts
`assets/databases/yatri.db` into `temp.fignore/yatri/`.

In CI, `.github/workflows/yatri-platforms.yml` builds the database from the newest snapshots, tries the
same Yatri steps, and uploads a release as a workflow artifact. The timetable watcher starts it on its
`watch/<railway>` branch whenever it pushes a new snapshot; it can also be run by hand. It reads the
Google Play secrets and the switch `MERGE_YATRI_PLATFORMS` from the `Act` environment: only when the
switch is `true` does the release carry the platform and rake tables (`mumbailocal release
--merge-layers`). Otherwise the release is official data only and Yatri's tables stay on the runner.
A Yatri failure never blocks the official release.

## Running the app locally

The app downloads its timetable the way it will in production: it fetches a release manifest,
then the gzipped SQLite file next to it, and checks both SHA-256 hashes. Locally, a mock of GitHub
Releases serves `pipeline/build/releases/`:

```sh
mise run data-server     # http://127.0.0.1:8787 (mock GitHub Releases)
mise run dev             # http://127.0.0.1:5173 (the PWA)
```

On a phone on the same Wi-Fi, use `mise run dev-lan` in place of `mise run dev` and open
`http://<laptop-ip>:5173`. The app proxies `/data` to the release server, so only port 5173 needs to be
reachable. Plain HTTP on a LAN address isn't a secure context, so the app uses IndexedDB and a built-in
SHA-256 there, and the service worker (the offline app shell) only runs on HTTPS or localhost.

To try the update path, run `mise run release -- --tag <new-tag>` while the app is open, then
use Settings → Offline timetable → Check for updates.

## Publishing

Merging to `main` publishes (`.github/workflows/publish.yml`):

1. If the timetable inputs changed (a merged watcher PR, a parser change), `yatri-platforms.yml` rebuilds
   the database and creates a **GitHub Release** `data-<date>-<hash>` marked latest, holding
   `manifest.json` and `mumbai-local.sqlite.gz`. It skips publishing when the latest release already
   holds the same data (`data_sha256` in the manifest ignores the build time).
2. The app is built with `BASE_PATH=/rahi` and deployed to **GitHub Pages** with the latest release's
   files at `data/latest/`, which is where the app reads them (`VITE_DATA_MANIFEST_URL`). GitHub Release
   downloads send no CORS header, so a browser cannot fetch them directly; the Release is the archive.

Pages is off until the repository variable `DEPLOY_PAGES` is `true` and Settings → Pages → Source is
"GitHub Actions" (a private repository needs a paid plan for Pages). Run it by hand from
Actions → Publish.
