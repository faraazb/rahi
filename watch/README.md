# Timetable watcher

Western and Central Railway publish the Mumbai suburban timetable as PDFs on their
websites, without a feed or announcement. This watcher checks those pages daily and
turns any change into a pull request for human review.

## Flow

```
daily 07:00 IST (cron)  or  manual run
        │
        ▼
watch/watch.py <railway>      fetch index pages (primary host, then old* mirror)
        │                     HEAD every linked PDF, compare with watch/state/<railway>.json
        │
        ├── page or PDF unreachable ──► issue "Timetable watcher: cannot check …"
        │                               (updated quietly while it persists, closed on recovery;
        │                                last good state is kept, nothing counts as removed)
        │
        └── added / modified / removed ─► full snapshot in data/raw/<railway>/<date>/
                                          + updated state, on branch watch/<railway>
                                          ──► one PR per railway, updated in place
                                          ──► starts .github/workflows/yatri-platforms.yml on
                                              that branch: build, Yatri platforms if
                                              MERGE_YATRI_PLATFORMS allows, release artifact,
                                              summary comment on the PR
```

- **Merge the PR** to accept the new snapshot and publish it: the merge to `main` runs
  `.github/workflows/publish.yml` (GitHub Release, then Pages). Before that, the preview build
  started on the branch comments on the PR with the release it built and how well Yatri's
  platforms matched.
- **Close the PR without merging** to dismiss it. It reopens only if the source changes again.
- Each PDF is saved under the sheet name the parsers expect (`dn.pdf`, `hb_up.pdf`, ...), chosen
  by the first matching regex in the `sheets` rules of `sources.json`. PDFs that are not sheets
  (old Harbour copies on the WR page, the abbreviations legend), or that match no rule, go to
  `other/`, which the parsers do not read. Unmatched PDFs and two PDFs claiming one sheet are
  listed under **Needs attention** in the PR. `SOURCES.txt` keeps each file's original URL; the
  pipeline reads the w.e.f. date from it (`pipeline/src/mumbailocal/editions.py`).
- The snapshot folder is named after the newest `Last-Modified` among the changed PDFs, moved to
  the day after the newest existing folder if it would sort before it (the build uses the newest
  folder). Daily reruns therefore keep the same folder name.
- Files are keyed by URL path, so a switch between `wr.` and `oldwr.` is not reported as a change.

## Files

| File | Purpose |
|---|---|
| `sources.json` | Pages to watch, host fallback order, minimum PDF count (detects layout changes), and the `sheets` rules that name each PDF |
| `state/<railway>.json` | Last accepted state: per PDF its ETag, Last-Modified, size, sha256 and first-seen date |
| `watch.py` | The check (Python standard library only) |
| `publish.sh` | Turns a run into a branch, PR and issue (uses `git`, `gh`, `jq`) |

## Running locally

```sh
python3 watch/watch.py wr --out /tmp/watch-out              # writes state + data/raw if changed
python3 watch/watch.py cr --out /tmp/watch-out --forget PUNE  # pretend matching files are new
```

## Testing in Actions

Run **Actions → Watch timetables → Run workflow** and set `forget` to a path substring (for
example `PUNE-LNL`). That file is treated as new, so the run opens a real PR. Close it
without merging afterwards.

## Repository settings this needs

- Settings → Actions → General → Workflow permissions: **Allow GitHub Actions to create and
  approve pull requests**.
- PRs opened with the default `GITHUB_TOKEN` do not trigger other workflows, so the watcher
  starts the build with `gh workflow run` (workflow_dispatch is exempt; needs `actions: write`).
