# wehoop-wnba-raw

## wehoop ESPN WNBA workflow diagram

```mermaid
  graph LR;
    A[wehoop-wnba-raw]-->B[wehoop-wnba-data];
    B[wehoop-wnba-data]-->C1[espn_wnba_schedules];
    B[wehoop-wnba-data]-->C2[espn_wnba_pbp];
    B[wehoop-wnba-data]-->C3[espn_wnba_team_boxscores];
    B[wehoop-wnba-data]-->C4[espn_wnba_player_boxscores];
    B[wehoop-wnba-data]-->C5[espn_wnba_rosters];
    B[wehoop-wnba-data]-->C6[espn_wnba_game_rosters];
    B[wehoop-wnba-data]-->C7[espn_wnba_player_core];
    B[wehoop-wnba-data]-->C8[espn_wnba_player_season_stats];
    B[wehoop-wnba-data]-->C9[espn_wnba_team_season_stats];
    B[wehoop-wnba-data]-->C10[espn_wnba_standings];
    B[wehoop-wnba-data]-->C11[espn_wnba_officials];
    B[wehoop-wnba-data]-->C12[espn_wnba_shots];
    B[wehoop-wnba-data]-->C13[espn_wnba_draft];
    B[wehoop-wnba-data]-->C14[wnba_crosswalk];
```

```mermaid
flowchart TB;
    subgraph A[wehoop-wnba-raw];
        direction TB;
        A0[scripts/daily_wnba_scraper.sh]-->A1[python/espn_wnba_01_schedules_scrape.py];
        A1[python/espn_wnba_01_schedules_scrape.py]-->A2[python/espn_wnba_02_pbp_scrape.py];
        A2[python/espn_wnba_02_pbp_scrape.py]-->A3[python/espn_wnba_03_standings_scrape.py];
        A3[python/espn_wnba_03_standings_scrape.py]-->A4[python/espn_wnba_04_game_rosters_scrape.py];
        A4[python/espn_wnba_04_game_rosters_scrape.py]-->A5[python/espn_wnba_05_draft_scrape.py];
        A5[python/espn_wnba_05_draft_scrape.py]-->A6[python/espn_wnba_06_player_stats_scrape.py];
        A6[python/espn_wnba_06_player_stats_scrape.py]-->A7[python/espn_wnba_07_team_stats_scrape.py];
        A7[python/espn_wnba_07_team_stats_scrape.py]-->A8[python/espn_wnba_08_team_rosters_scrape.py];
        A8[python/espn_wnba_08_team_rosters_scrape.py]-->A9[python/espn_wnba_09_player_core_scrape.py];
        A9[python/espn_wnba_09_player_core_scrape.py]-->A10[python/espn_wnba_10_officials_scrape.py];
    end;

    subgraph B[wehoop-wnba-data];
        direction TB;
        B0[scripts/daily_wnba_data_processor.sh]-->B1[python/espn_wnba_01_pbp_creation.py];
        B1[python/espn_wnba_01_pbp_creation.py]-->B2[python/espn_wnba_02_team_box_creation.py];
        B2[python/espn_wnba_02_team_box_creation.py]-->B3[python/espn_wnba_03_player_box_creation.py];
        B3[python/espn_wnba_03_player_box_creation.py]-->B4[python/espn_wnba_04_rosters_creation.py];
        B4[python/espn_wnba_04_rosters_creation.py]-->B5[python/espn_wnba_05_player_season_stats_creation.py];
        B5[python/espn_wnba_05_player_season_stats_creation.py]-->B6[python/espn_wnba_06_team_season_stats_creation.py];
        B6[python/espn_wnba_06_team_season_stats_creation.py]-->B7[python/espn_wnba_07_standings_creation.py];
        B7[python/espn_wnba_07_standings_creation.py]-->B8[python/espn_wnba_08_draft_creation.py];
        B8[python/espn_wnba_08_draft_creation.py]-->B9[python/espn_wnba_09_game_rosters_creation.py];
        B9[python/espn_wnba_09_game_rosters_creation.py]-->B10[python/espn_wnba_10_officials_creation.py];
        B10[python/espn_wnba_10_officials_creation.py]-->B11[python/espn_wnba_11_team_crosswalk_creation.py];
        B11[python/espn_wnba_11_team_crosswalk_creation.py]-->B12[python/espn_wnba_12_schedule_crosswalk_creation.py];
        B12[python/espn_wnba_12_schedule_crosswalk_creation.py]-->B13[python/espn_wnba_13_player_crosswalk_creation.py];
        B13[python/espn_wnba_13_player_crosswalk_creation.py]-->B14[python/espn_wnba_14_schedules_creation.py];
        B14[python/espn_wnba_14_schedules_creation.py]-->B15[python/espn_wnba_15_shots_creation.py];
        B15[python/espn_wnba_15_shots_creation.py]-->B16[python/espn_wnba_16_player_core_creation.py];
    end;

    subgraph C[sportsdataverse-data Releases];
        direction TB;
        C1[espn_wnba_schedules];
        C2[espn_wnba_pbp];
        C3[espn_wnba_team_boxscores];
        C4[espn_wnba_player_boxscores];
        C5[espn_wnba_rosters];
        C6[espn_wnba_game_rosters];
        C7[espn_wnba_player_core];
        C8[espn_wnba_player_season_stats];
        C9[espn_wnba_team_season_stats];
        C10[espn_wnba_standings];
        C11[espn_wnba_officials];
        C12[espn_wnba_shots];
        C13[espn_wnba_draft];
        C14[wnba_crosswalk];
    end;

    A-->B;
    B-->C;
```

`scripts/daily_wnba_scraper.sh` and `scripts/daily_wnba_data_processor.sh` are the
daily drivers (the `00` role); stage numbers are intended build order, not run order.
`scripts/annual_wnba_draft_scraper.sh` covers the mid-April draft the daily cron window misses.

[wehoop-wbb-raw repository (source: ESPN)](https://github.com/sportsdataverse/wehoop-wbb-raw)

[wehoop-wbb-data repository (source: ESPN)](https://github.com/sportsdataverse/wehoop-wbb-data)

[wehoop-wnba-raw repository (source: ESPN)](https://github.com/sportsdataverse/wehoop-wnba-raw)

[wehoop-wnba-data repository (source: ESPN)](https://github.com/sportsdataverse/wehoop-wnba-data)

[wehoop-wnba-stats-raw repository (source: WNBA Stats)](https://github.com/sportsdataverse/wehoop-wnba-stats-raw)

[wehoop-wnba-stats-data repository (source: WNBA Stats)](https://github.com/sportsdataverse/wehoop-wnba-stats-data)

[ncaa-wbb-hoops-raw repository (source: stats.ncaa.org)](https://github.com/sportsdataverse/ncaa-wbb-hoops-raw)

[ncaa-wbb-hoops-data repository (source: stats.ncaa.org)](https://github.com/sportsdataverse/ncaa-wbb-hoops-data)

## Women's Basketball Data Releases

[ESPN Women's College Basketball Schedules](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_womens_college_basketball_schedules)

[ESPN Women's College Basketball PBP](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_womens_college_basketball_pbp)

[ESPN Women's College Basketball Team Boxscores](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_womens_college_basketball_team_boxscores)

[ESPN Women's College Basketball Player Boxscores](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_womens_college_basketball_player_boxscores)

[ESPN WNBA Schedules](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_wnba_schedules)

[ESPN WNBA PBP](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_wnba_pbp)

[ESPN WNBA Team Boxscores](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_wnba_team_boxscores)

[ESPN WNBA Player Boxscores](https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/espn_wnba_player_boxscores)


## Repository layout

<!-- BEGIN GENERATED: layout -->

```
wehoop-wnba-raw/
├── logs/   # per-run logs (gitignored where large)
├── ops/   # cron definitions and runbooks
│   └── oneoff/
├── python/   # Python pipeline stages, numbered in build order
│   ├── espn_wnba_01_schedules_scrape.py
│   ├── espn_wnba_02_pbp_scrape.py
│   ├── espn_wnba_03_standings_scrape.py
│   ├── espn_wnba_04_game_rosters_scrape.py
│   ├── espn_wnba_05_draft_scrape.py
│   ├── espn_wnba_06_player_stats_scrape.py
│   ├── espn_wnba_07_team_stats_scrape.py
│   ├── espn_wnba_08_team_rosters_scrape.py
│   ├── espn_wnba_09_player_core_scrape.py
│   └── espn_wnba_10_officials_scrape.py
├── scripts/   # bash drivers (the daily/weekly entry points)
│   ├── _venv.sh
│   ├── annual_wnba_draft_scraper.sh
│   └── daily_wnba_scraper.sh
├── tests/   # test suite
│   ├── test_cli_contract.py
│   ├── test_payload_schemas.py
│   ├── test_persist_guard.py
│   ├── test_schedule_master.py
│   └── test_scripts_importable.py
└── wnba/
    ├── draft/
    ├── game_rosters/
    ├── json/
    ├── officials/
    ├── player_core/
    ├── player_season_stats/
    ├── schedules/
    ├── standings/
    └── … 2 more
```

<!-- END GENERATED: layout -->

## Reports & explainers

<!-- BEGIN GENERATED: reports -->

| Report | What it is | Last updated |
|---|---|---|
| _none yet_ | — | — |

<!-- END GENERATED: reports -->

## Automation & status

<!-- BEGIN GENERATED: status -->

| workflow | schedule | last run |
|---|---|---|
| [![daily_wnba_raw.yml](https://github.com/sportsdataverse/wehoop-wnba-raw/actions/workflows/daily_wnba_raw.yml/badge.svg)](https://github.com/sportsdataverse/wehoop-wnba-raw/actions/workflows/daily_wnba_raw.yml) | days 1-12 06:30 UTC in May-Oct | 2026-08-12 |
| [![orphan_scripts.yml](https://github.com/sportsdataverse/wehoop-wnba-raw/actions/workflows/orphan_scripts.yml/badge.svg)](https://github.com/sportsdataverse/wehoop-wnba-raw/actions/workflows/orphan_scripts.yml) | on push / PR / dispatch | 2026-08-24 |
| [![wehoop_wnba_data_trigger.yml](https://github.com/sportsdataverse/wehoop-wnba-raw/actions/workflows/wehoop_wnba_data_trigger.yml/badge.svg)](https://github.com/sportsdataverse/wehoop-wnba-raw/actions/workflows/wehoop_wnba_data_trigger.yml) | on push / dispatch | 2026-08-31 |
| [![wehoop_wnba_draft_trigger.yml](https://github.com/sportsdataverse/wehoop-wnba-raw/actions/workflows/wehoop_wnba_draft_trigger.yml/badge.svg)](https://github.com/sportsdataverse/wehoop-wnba-raw/actions/workflows/wehoop_wnba_draft_trigger.yml) | on push / dispatch | 2026-05-11 |

<!-- END GENERATED: status -->

## Consumers

The packages that read what this repo produces:

- **R:** [wehoop](https://wehoop.sportsdataverse.org) — docs at <https://wehoop.sportsdataverse.org>
- **Python:** [`sportsdataverse.wnba`](https://github.com/sportsdataverse/sportsdataverse-py) — docs at <https://py.sportsdataverse.org>

## Stage inventory

Every numbered pipeline stage in `python/` (auto-listed; run subsets with the `scripts/*.sh` drivers by number or name):

- `python/espn_wnba_01_schedules_scrape.py`
- `python/espn_wnba_02_pbp_scrape.py`
- `python/espn_wnba_03_standings_scrape.py`
- `python/espn_wnba_04_game_rosters_scrape.py`
- `python/espn_wnba_05_draft_scrape.py`
- `python/espn_wnba_06_player_stats_scrape.py`
- `python/espn_wnba_07_team_stats_scrape.py`
- `python/espn_wnba_08_team_rosters_scrape.py`
- `python/espn_wnba_09_player_core_scrape.py`
- `python/espn_wnba_10_officials_scrape.py`
