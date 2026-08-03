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
        python3 python/espn_wnba_05_draft_scrape.py -s $i -e $i -r $RESCRAPE
        git pull >> /dev/null
        git add wnba/draft >> /dev/null
        git pull >> /dev/null
        git add . >> /dev/null
        git commit -m "WNBA Draft Update (Start: $i End: $i)" || echo "No changes to commit"
        git pull >> /dev/null
        git push >> /dev/null
    } 2>&1 | tee "$TMPLOG"

    # Block is finished and pushed; tee has closed $TMPLOG. Keep a local copy
    # under logs/ (gitignored since 66c07f883 -- run logs are no longer
    # committed, so there is no log commit/push here). Mirrors the daily driver.
    cp "$TMPLOG" "$LOGFILE"
    rm -f "$TMPLOG"
done
