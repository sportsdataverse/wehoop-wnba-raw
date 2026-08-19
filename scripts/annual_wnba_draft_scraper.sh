#!/bin/bash
# Scrape raw WNBA draft results per season.
#
# The draft has annual cadence (not daily) and writes to
# wnba/draft/json/{season}.json. A push touching that path fires
# .github/workflows/wehoop_wnba_draft_trigger.yml (event-type
# annual_wnba_draft) which wakes the downstream draft pipeline in
# wehoop-wnba-data. Run this once per draft cycle, not on the daily
# cron — rolling it into scripts/daily_wnba_scraper.sh would re-trigger
# the downstream pipeline 365 times a year for no benefit.
#
# Usage: bash scripts/annual_wnba_draft_scraper.sh -s 2024 -e 2024 [-r false]


# Commit + push, surviving a remote that moved while the build was running.
#
# Pulling BEFORE staging can only abort: the build has just rewritten tracked
# parquet/csv/json, so `git pull` refuses with "Your local changes would be
# overwritten by merge". The old form then committed anyway, pushed into a
# non-fast-forward rejection, and swallowed it -- a GREEN job that published
# nothing (wehoop-wnba-data 32192069433/32192069566, hoopR-nba-data 32204419012).
#
# Stage and commit FIRST so the tree is clean, then reconcile. `rebase --merge`
# rather than `pull --rebase`: the default am backend base64-encodes every blob
# it replays, which crawls on these binary-asset repos.
sdv_commit_push() {
  local msg="$1"; shift
  git add -- "$@" >/dev/null 2>&1 || true
  if git diff --cached --quiet; then
    echo "nothing to commit for: $msg"
    return 0
  fi
  git commit -m "$msg" >/dev/null || { echo "::warning ::commit failed: $msg"; return 1; }
  local attempt
  for attempt in 1 2 3; do
    if git push origin HEAD >/dev/null 2>&1; then
      echo "pushed: $msg (attempt $attempt)"
      return 0
    fi
    echo "push rejected (attempt $attempt); syncing with origin"
    git fetch --quiet origin main || true
    if ! git rebase --merge origin/main >/dev/null 2>&1; then
      git rebase --abort >/dev/null 2>&1 || true
      echo "::error ::cannot rebase onto origin/main for: $msg"
      return 1
    fi
  done
  echo "::error ::push still rejected after 3 attempts: $msg"
  return 1
}

while getopts s:e:r: flag
do
    case "${flag}" in
        s) START_YEAR=${OPTARG};;
        e) END_YEAR=${OPTARG};;
        r) RESCRAPE=${OPTARG};;
    esac
done

RESCRAPE=${RESCRAPE:-true}
echo "Rescrape set to: $RESCRAPE"
mkdir -p logs

# Resolve the interpreter the same way the daily driver does. This used to be a
# bare `python3`, which on a host whose .venv had been swept resolved to the
# ambient 3.8 and its years-old sportsdataverse -- the annual cadence just means
# the breakage would have waited until draft night to show up.
# shellcheck source=scripts/_venv.sh
. "$(dirname "${BASH_SOURCE[0]}")/_venv.sh"
PY="$SDV_PY"
echo "Interpreter: $PY"
sdv_preflight sportsdataverse.wnba
for i in $(seq "${START_YEAR}" "${END_YEAR}")
do
    LOGFILE="logs/wehoop_wnba_draft_logfile_${i}.log"
    TMPLOG=$(mktemp "/tmp/wehoop_wnba_draft_logfile_${i}.XXXXXX.log")
    echo "=== Processing draft $i ==="
    # Tee inside the block writes to /tmp (untracked) so the `git pull` calls
    # don't trip over their own log output being written to a tracked file.
    {
        git pull >> /dev/null
        git config --local user.email "action@github.com"
        git config --local user.name "Github Action"
        $PY python/espn_wnba_05_draft_scrape.py -s $i -e $i -r $RESCRAPE
        sdv_commit_push "WNBA Draft Update (Start: $i End: $i)" wnba/draft || PUSH_RC=1
    } 2>&1 | tee "$TMPLOG"

    # Block is finished and pushed; tee has closed $TMPLOG. Keep a local copy
    # under logs/ (gitignored since 66c07f883 -- run logs are no longer
    # committed, so there is no log commit/push here). Mirrors the daily driver.
    cp "$TMPLOG" "$LOGFILE"
    rm -f "$TMPLOG"
done

# A rejected push is a FAILED run, not a green one. Release assets upload on a
# separate path and can succeed while the repo mirror is left stale.
if [ "${PUSH_RC:-0}" != "0" ]; then
  echo "::error ::At least one commit failed to reach origin; the repo mirror is stale."
  exit 1
fi
