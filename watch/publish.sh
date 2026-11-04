#!/usr/bin/env bash
# Turn one watch.py run into GitHub state. Runs inside the Action after watch.py.
#
#   errors   -> open (or quietly update) one issue per railway; close it on a clean run
#   changes  -> commit state + snapshot to branch watch/<railway>, open or update one PR
#
# Idempotent: the daily run force-pushes only when the branch's content would change,
# and a PR you closed without merging is not reopened for the same content.
#
# Usage: publish.sh <railway> <out-dir>     (needs GH_TOKEN and GITHUB_REPOSITORY)
set -euo pipefail

rly="$1"
out="$2"
result="$out/result.json"
name=$(jq -r .name "$result")
branch="watch/$rly"
issue_title="Timetable watcher: cannot check $name"
issue_label="source-broken"
pr_label="timetable-update"

summary() { echo "$*" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"; }

# --------------------------------------------------------------------- issues
n_err=$(jq '.errors | length' "$result")
issue=$(gh issue list --state open --label "$issue_label" --json number,title \
          --jq ".[] | select(.title == \"$issue_title\") | .number" | head -n1)
if [[ "$n_err" -gt 0 ]]; then
  if [[ -n "$issue" ]]; then
    gh issue edit "$issue" --body-file "$out/errors.md" >/dev/null
    summary "Errors: updated issue #$issue"
  else
    gh label create "$issue_label" --color B60205 --force \
      --description "Timetable source unreachable or changed shape" >/dev/null
    url=$(gh issue create --title "$issue_title" --label "$issue_label" --body-file "$out/errors.md")
    summary "Errors: opened $url"
  fi
elif [[ -n "$issue" ]]; then
  gh issue close "$issue" --reason completed \
    --comment "Clean run on $(date -u +%F): all $name pages and PDFs reachable." >/dev/null
  summary "Recovered: closed issue #$issue"
fi

# ------------------------------------------------------------------------ PRs
if [[ "$(jq -r .changed "$result")" != "true" ]]; then
  summary "$name: no timetable changes."
  exit 0
fi

snapshot=$(jq -r .snapshot "$result")
git switch -c "$branch"
git add "watch/state/$rly.json" "$snapshot"
counts=$(jq -r '.counts | "\(.added) added, \(.modified) modified, \(.removed) removed"' "$result")
git commit -q -m "data($rly): timetable PDFs changed ($counts)" \
  -m "Snapshot: $snapshot" -m "Detected by watch/watch.py."

remote_sha=$(git ls-remote origin "refs/heads/$branch" | cut -f1)
if [[ -n "$remote_sha" ]] && git fetch -q origin "$branch" \
     && [[ "$(git rev-parse "FETCH_HEAD^{tree}")" == "$(git rev-parse "HEAD^{tree}")" ]]; then
  summary "Branch $branch already holds this exact change; not pushing."
  head_sha="$remote_sha"
else
  git push -q --force origin "$branch"
  head_sha=$(git rev-parse HEAD)
  summary "Pushed $branch ($head_sha)."
fi

title="$name timetable update: $counts"
open_pr=$(gh pr list --head "$branch" --state open --json number --jq '.[0].number // empty')
if [[ -n "$open_pr" ]]; then
  gh pr edit "$open_pr" --title "$title" --body-file "$out/report.md" >/dev/null
  summary "Updated PR #$open_pr."
  exit 0
fi

dismissed=$(gh pr list --head "$branch" --state closed --json number,headRefOid \
              --jq ".[] | select(.headRefOid == \"$head_sha\") | .number" | head -n1)
if [[ -n "$dismissed" ]]; then
  summary "PR #$dismissed for this exact change was closed; not reopening."
  exit 0
fi

gh label create "$pr_label" --color 0E8A16 --force \
  --description "New timetable PDFs detected by the watcher" >/dev/null
url=$(gh pr create --base main --head "$branch" --title "$title" \
        --body-file "$out/report.md" --label "$pr_label")
summary "Opened $url"
