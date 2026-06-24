# CLAUDE.md — wehoop-wnba-raw

Python scraper for ESPN WNBA. Commits raw per-game ESPN JSON to git; the paired
`wehoop-wnba-data` (R) reshapes it into release parquet/csv/rds consumed by the
`wehoop` R package's `load_wnba_*()` loaders.

Pipeline: `ESPN -> wehoop-wnba-raw [HERE] --push--> wehoop-wnba-data --release--> sportsdataverse-data --> wehoop`.

## Commands (verified)

Driven by `scripts/daily_wnba_scraper.sh` (getopts `-s -e -r`; loops seasons,
commits + pushes). Scrapers take `--start_year/-s`, `--end_year/-e`,
`--rescrape/-r`. Seasons are integer years.

```sh
bash scripts/daily_wnba_scraper.sh -s 2025 -e 2025 -r false   # full daily flow
python3 python/scrape_wnba_schedules.py -s 2025 -e 2025 -r false
python3 python/scrape_wnba_json.py      -s 2025 -e 2025 -r false   # per-game PBP JSON
# also: scrape_wnba_team_rosters / _player_stats / _team_stats / _standings /
#       _game_rosters / _officials  (same -s -e -r flags)
python3 python/scrape_wnba_draft.py     -s 2025 -e 2025 [-r]   # annual; own trigger (NOT in daily flow)
# helper: wnba_pbp_creation.py (PBP prototype, not in daily flow)
```

`-r true` re-scrapes games already on disk; `-r false` skips them. Scrapers
depend on `sportsdataverse-py` (`requirements.txt`) and call
`sdv.wnba.espn_wnba_*(..., raw=True)` — fix ESPN parsing in `sportsdataverse-py`, not here.

## Outputs (committed to git, under `wnba/`)

- `wnba/schedules/{rds,csv,parquet}/wnba_schedule_{year}.{ext}`
- `wnba/json/final/{game_id}.json` — clean payload consumed by `wehoop-wnba-data`
- `wnba/json/raw/{game_id}.json` — raw ESPN response (forensics); `wnba/errors/` — failed games
- `wnba/{team_rosters,player_season_stats,team_stats,standings}/json/...` (season-keyed)
- `wnba/draft/json/{season}.json` (annual)
- `wnba/{game_rosters,officials}/json/{game_id}.json` (per-game)

## CI

- `.github/workflows/daily_wnba_raw.yml` — cron (in-season windows, `0 5 UTC`,
  2h before the data repo's parser); runs all daily scrapers then one
  `git add wnba/` + commit + push. `workflow_dispatch` inputs
  `start_year`/`end_year`/`rescrape`. Draft is excluded — it has its own pipeline.
- `.github/workflows/wehoop_wnba_data_trigger.yml` — on push to `wnba/**`
  (excluding `wnba/draft/**`), fires `repository_dispatch` event-type
  `daily_wnba_data` at `sportsdataverse/wehoop-wnba-data`.
- `.github/workflows/wehoop_wnba_draft_trigger.yml` — on push to
  `wnba/draft/json/**`, fires event-type `annual_wnba_draft` at the same data repo.

## Gotchas

- Daily commit subject `"WNBA Raw Updated (Start: $i End: $i)"` is load-bearing —
  the data repo regex-extracts the years from `Start:`/`End:`. Don't restyle it.
- Draft is split off its own trigger so a draft push doesn't fire the daily data pipeline. Keep them separate.
- `-raw` commits raw per-game JSON to git intentionally (the SDV pattern); the tree is large by design.
- Never add AI co-author trailers to commits. Use Conventional Commits (`feat(scrape):`, `fix(scrape):`, `ci:`).
