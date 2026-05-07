# wehoop-wnba-raw Copilot Instructions

## Project Context

This repo is the Python ESPN-scrape stage for the WNBA. It writes
per-game JSON under `wnba/json/final/{game_id}.json` and commits results
to `main`. Every push wakes the downstream R parser in `wehoop-wnba-data`
via `repository_dispatch` (event-type `daily_wnba_data`, defined in
`.github/workflows/wehoop_wnba_data_trigger.yml`).

Pipeline: `ESPN -> wehoop-wnba-raw [HERE] -> wehoop-wnba-data -> sportsdataverse-data -> wehoop`.

Do not confuse with `wehoop-wnba-stats-raw` — that's a placeholder for the
WNBA Stats API, which has no raw cache.

## Repository Workflow

- Branch from `main`; `main` is the default and release branch.
- The CI entry point is `scripts/daily_wnba_scraper.sh -s <START> -e <END> -r <true|false>`.
- Scrapers shell out to `sportsdataverse-py`. Fix ESPN parser bugs upstream there, not here.
- Don't reorganize the `wnba/` output tree without aligning `wehoop-wnba-data/R/espn_wnba_0[1-3]_*.R`.

## Build & Development Commands

```sh
bash scripts/daily_wnba_scraper.sh -s 2025 -e 2025 -r false
python3 python/scrape_wnba_schedules.py    -s 2025 -e 2025 -r false
python3 python/scrape_wnba_json.py         -s 2025 -e 2025 -r false
python3 python/scrape_wnba_team_rosters.py -s 2025 -e 2025
python3 python/scrape_wnba_player_stats.py -s 2025 -e 2025
python3 python/scrape_wnba_team_stats.py   -s 2025 -e 2025
python3 python/scrape_wnba_standings.py    -s 2025 -e 2025
python3 python/scrape_wnba_draft.py        -s 2025 -e 2025   # annual; fires wehoop_wnba_draft_trigger.yml
python3 python/scrape_wnba_game_rosters.py -s 2025 -e 2025
python3 python/scrape_wnba_officials.py    -s 2025 -e 2025
```

`-r true` forces re-scrape; `-r false` skips files already on disk. Outputs:

- `wnba/schedules/{rds,csv,parquet}/wnba_schedule_{year}.{ext}`
- `wnba/json/final/{game_id}.json` (consumed downstream)
- `wnba/json/raw/{game_id}.json`, `wnba/errors/` (forensics)
- `wnba/team_rosters/json/{season}/{team_id}.json` (Phase 1)
- `wnba/player_season_stats/json/{season}/{athlete_id}.json` (Phase 1)
- `wnba/team_stats/json/{season}/{team_id}.json` — ESPN per-team season stats (daily)
- `wnba/standings/json/{season}.json` — ESPN per-season standings (daily)
- `wnba/draft/json/{season}.json` — ESPN per-season draft results (annual; fires `wehoop_wnba_draft_trigger.yml`)
- `wnba/game_rosters/json/{game_id}.json` — ESPN per-game rosters (daily; per-game iteration)
- `wnba/officials/json/{game_id}.json` — ESPN per-game officials (daily; per-game iteration)

## Code Style

- Follow the parent SDK's Python conventions: snake_case, 4-space indent.
- Prefer `pathlib.Path`, `concurrent.futures` for parallelism, `tqdm` for progress.
- Don't add bespoke ESPN parsing here — call into `sportsdataverse.wnba.*` and persist its output.
- Keep `requirements.txt` minimal.

## Daily Umbrella Workflow

`.github/workflows/daily_wnba_raw.yml` runs every WNBA scraper sequentially
on a single GitHub Actions cron and commits the cumulative output in one
push, which fires `wehoop_wnba_data_trigger.yml` exactly once per run.

- Cron `0 5 UTC` daily, gated to the in-season windows used by
  `wehoop-wnba-data/daily_wnba.yml` (late Oct, Nov-Dec, Jan-Jun, early Jul).
- `workflow_dispatch` inputs: `start_year`, `end_year`, `rescrape`.
- Scripts in order: `scrape_wnba_schedules.py`, `scrape_wnba_json.py`,
  `scrape_wnba_team_rosters.py`, `scrape_wnba_player_stats.py`,
  `scrape_wnba_team_stats.py`, `scrape_wnba_standings.py`,
  `scrape_wnba_game_rosters.py`, `scrape_wnba_officials.py`.
- `scrape_wnba_draft.py` is intentionally excluded — it has its own annual
  trigger (`wehoop_wnba_draft_trigger.yml`) and shouldn't fire daily.
- Single `git add wnba/` + commit + push at the end keeps the downstream
  dispatch count to one per run.
- Eventually replaces `scripts/daily_wnba_scraper.sh` for CI use; the
  shell script remains for local + external scheduler invocation.

## Cross-Repo References

- Shared conventions: <https://github.com/sportsdataverse/wehoop/blob/main/CLAUDE.md>
- SDK internals: <https://github.com/sportsdataverse/sportsdataverse-py/blob/main/CLAUDE.md>

## Conventional Commits

Use: `type(scope): description`. Common types: `feat`, `fix`, `chore`, `ci`, `docs`, `refactor`. Use `type!:` or a `BREAKING CHANGE:` footer for breaking changes.

**Important: Never include AI agents or assistants (e.g., Claude, Copilot, Cursor, GPT, Gemini) as co-authors on commits.** Omit all `Co-Authored-By` trailers referencing AI tools. This applies whether the change was generated, refactored, or reviewed with AI assistance — the human author is the sole attributable contributor.
