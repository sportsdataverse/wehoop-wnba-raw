# CLAUDE.md — wehoop-wnba-raw Development Guide

## Repo Overview

`wehoop-wnba-raw` is the Python-side scraper for ESPN WNBA play-by-play
JSON. It pulls per-season schedules, then per-game JSON, persists them
under `wnba/schedules/` and `wnba/json/final/{game_id}.json`, and commits
them back to this repo. Every push to `main` fires a `repository_dispatch`
that wakes the downstream R parser in `wehoop-wnba-data`. This repo is
the authoritative cache of raw ESPN WNBA payloads.

## Pipeline Position

```
ESPN APIs --[python scrape]--> wehoop-wnba-raw [HERE]
                                    | push trigger
                                    v
                               wehoop-wnba-data --[release upload]--> sportsdataverse-data
                                                                          | piggyback
                                                                          v
                                                                    wehoop R package
```

The push trigger lives in `.github/workflows/wehoop_wnba_data_trigger.yml`
and fires `repository_dispatch` event-type `daily_wnba_data` against
`sportsdataverse/wehoop-wnba-data`.

## Build & Development Commands

The repo is driven by `scripts/daily_wnba_scraper.sh`, which sequences
schedule scrape then per-game JSON scrape then commit + push:

```sh
# Full daily flow for one or more seasons (CI entry point)
bash scripts/daily_wnba_scraper.sh -s 2025 -e 2025 -r false

# Or call the scrapers directly when iterating
python3 python/scrape_wnba_schedules.py -s 2025 -e 2025 -r false
python3 python/scrape_wnba_json.py      -s 2025 -e 2025 -r false

# Helper (PBP creation prototype, not in the daily flow)
python3 python/wnba_pbp_creation.py

# Phase 1 datasets (per-season rosters + per-athlete season stats)
python3 python/scrape_wnba_team_rosters.py -s 2025 -e 2025 [-r]
python3 python/scrape_wnba_player_stats.py -s 2025 -e 2025 [-r]

# Per-team season stats and per-season standings (daily cadence)
python3 python/scrape_wnba_team_stats.py   -s 2025 -e 2025 [-r]
python3 python/scrape_wnba_standings.py    -s 2025 -e 2025 [-r]

# Annual draft scrape (runs once per draft, fires its own trigger workflow)
python3 python/scrape_wnba_draft.py        -s 2025 -e 2025 [-r]

# Per-game rosters and officials (per-game iteration; mirrors scrape_wnba_json.py shape)
python3 python/scrape_wnba_game_rosters.py -s 2025 -e 2025 [-r]
python3 python/scrape_wnba_officials.py    -s 2025 -e 2025 [-r]
```

`-r true` forces re-scrape of games already on disk; `-r false` skips
existing files. Output paths the scrapers write under:

- `wnba/schedules/{rds,csv,parquet}/wnba_schedule_{year}.{ext}`
- `wnba/json/final/{game_id}.json` — clean payload, consumed by `wehoop-wnba-data`
- `wnba/json/raw/{game_id}.json`   — raw ESPN response (kept for forensics)
- `wnba/errors/`                   — failed-game records
- `wnba/team_rosters/json/{season}/{team_id}.json`           — Phase 1: ESPN team-roster snapshots
- `wnba/player_season_stats/json/{season}/{athlete_id}.json` — Phase 1: ESPN per-athlete season stats
- `wnba/team_stats/json/{season}/{team_id}.json`             — ESPN per-team season stats (daily cadence)
- `wnba/standings/json/{season}.json`                        — ESPN per-season standings (daily cadence)
- `wnba/draft/json/{season}.json`                            — ESPN per-season draft results (annual cadence; fires its own `wehoop_wnba_draft_trigger.yml` workflow)
- `wnba/game_rosters/json/{game_id}.json`                    — ESPN per-game rosters (daily cadence; per-game iteration)
- `wnba/officials/json/{game_id}.json`                       — ESPN per-game officials (daily cadence; per-game iteration)

## Project Structure

```
python/
  scrape_wnba_schedules.py    # ESPN schedule scrape -> wnba/schedules/
  scrape_wnba_json.py         # Per-game JSON scrape -> wnba/json/final/{game_id}.json
  wnba_pbp_creation.py        # PBP compile prototype (not in daily flow)
scripts/
  daily_wnba_scraper.sh       # CI entry point
wnba/                         # Committed scraped output
.github/workflows/
  wehoop_wnba_data_trigger.yml   # Fires repository_dispatch (event-type daily_wnba_data) on push
  wehoop_wnba_draft_trigger.yml  # Fires repository_dispatch (event-type annual_wnba_draft) only when wnba/draft/json/** changes
  daily_wnba_raw.yml             # Umbrella daily scrape (cron + workflow_dispatch)
```

## Daily Umbrella Workflow

`.github/workflows/daily_wnba_raw.yml` is the in-repo cron entry point. It
runs every per-dataset Python scraper sequentially in one job and commits
the cumulative output in a single push, which then fires
`wehoop_wnba_data_trigger.yml` exactly once per run.

- **Cadence**: `0 5 UTC` daily, gated to the in-season month/day windows
  used by `wehoop-wnba-data/daily_wnba.yml` (late October, November-December,
  January-June, early July). The 2-hour offset before the data repo's
  `0 7 UTC` parser gives the scrape time to land before the parser pulls.
- **Manual run**: `workflow_dispatch` accepts `start_year`, `end_year`,
  and `rescrape` (default `false`) inputs.
- **Scripts run, in order**: `scrape_wnba_schedules.py`, `scrape_wnba_json.py`,
  `scrape_wnba_team_rosters.py`, `scrape_wnba_player_stats.py`,
  `scrape_wnba_team_stats.py`, `scrape_wnba_standings.py`,
  `scrape_wnba_game_rosters.py`, `scrape_wnba_officials.py`. All are invoked
  with the canonical `--start_year`/`--end_year` flags plus `-r $RESCRAPE`.
- **`scrape_wnba_draft.py` is intentionally excluded** — the draft has its
  own annual workflow (paired with `wehoop_wnba_draft_trigger.yml`).
  Including it here would re-trigger the draft pipeline daily for no benefit.
- **Single push**: `git add wnba/` + one commit + one push at the end. This
  is intentional — every push to `main` fires `wehoop_wnba_data_trigger.yml`,
  so one push per day means one downstream dispatch per day instead of eight.
- **Replaces**: `scripts/daily_wnba_scraper.sh` if/when CI moves wholly to
  GitHub Actions. The shell script is still callable locally and from
  external schedulers; nothing here removes it.

The Python scrapers depend on `sportsdataverse-py` (declared in
`requirements.txt`); they call `sdv.wnba.espn_wnba_pbp(game_id, raw=True)`
and similar. Bug fixes to ESPN parsing belong in `sportsdataverse-py` —
not here.

## Cross-Repo References

- Shared conventions and broader context: <https://github.com/sportsdataverse/wehoop/blob/main/CLAUDE.md>
- Python scraper internals (the SDK this repo calls): <https://github.com/sportsdataverse/sportsdataverse-py/blob/main/CLAUDE.md>
- Downstream parser: <https://github.com/sportsdataverse/wehoop-wnba-data>
- Sister repo (same shape, different sport): <https://github.com/sportsdataverse/wehoop-wbb-raw>

## Project-Specific Gotchas

- `python/scrape_wnba_json.py` writes JSON under `wnba/json/final/{game_id}.json`. Downstream `wehoop-wnba-data` reads from `https://raw.githubusercontent.com/sportsdataverse/wehoop-wnba-raw/main/wnba/...`, so the file paths and commit-to-main are load-bearing.
- The per-push `wehoop_wnba_data_trigger.yml` workflow only fires on `push` and `workflow_dispatch`. Force-pushes can land changes without firing downstream jobs — push normally.
- Do not confuse this with `wehoop-wnba-stats-raw` — that's a placeholder for the WNBA Stats API, which has no raw cache (the API IS the raw layer).
- ESPN JSON schema drift is handled in `sportsdataverse-py` (the call boundary). If a scraper starts dropping fields, fix the SDK first; this repo should stay thin.

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(scrape): add postseason ID range to scrape_wnba_schedules.py
fix(scrape): retry HTTP 429s in scrape_wnba_json with backoff
chore(deps): bump sportsdataverse-py pin in requirements.txt
ci: tighten secret scoping in wehoop_wnba_data_trigger.yml
```

Prefer scoped subjects (`feat(scrape): ...`, `ci(trigger): ...`). Use
`type!:` or a `BREAKING CHANGE:` footer for breaking changes. Split
unrelated work into separate commits.

**Important: Never include AI agents or assistants (e.g., Claude, Copilot, Cursor, GPT, Gemini) as co-authors on commits.** Omit all `Co-Authored-By` trailers referencing AI tools. This applies whether the change was generated, refactored, or reviewed with AI assistance — the human author is the sole attributable contributor.
