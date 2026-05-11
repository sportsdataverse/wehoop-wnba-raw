
"""Scrape ESPN WNBA team season stats per (season, team_id).

Output: ``wnba/team_stats/json/{season}/{team_id}.json`` -- raw ESPN
response. The downstream R parser in ``wehoop-wnba-data`` reads these
JSONs to build the per-season tidy team-stats frame.

Team ids are sourced from the same place ``scrape_wnba_team_rosters.py``
uses: the season's schedule parquet (``home_id`` / ``away_id``), with a
fallback to ``sdv.wnba.espn_wnba_teams`` if the parquet is missing.

Requirements:
    Depends on the ``espn_wnba_team_stats`` helper added to
    ``sportsdataverse-py`` (sportsdataverse/wnba/wnba_team_stats.py). The
    repo's ``requirements.txt`` should pin a version of sportsdataverse-py
    that exports it; until that release lands, install sdv-py from source
    (``pip install -e <path>/sdv-py``).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gc
import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd
import sportsdataverse as sdv
from tqdm import tqdm

# The new module is not yet re-exported from ``sportsdataverse.wnba``, so we
# import the function directly from its module to avoid relying on the
# top-level package surface.
from sportsdataverse.wnba.wnba_team_stats import espn_wnba_team_stats


logging.basicConfig(
    level=logging.INFO,
    filename="wehoop_wnba_raw_team_stats_logfile.txt",
)
logger = logging.getLogger(__name__)

PATH_TO_OUTPUT = "wnba/team_stats/json"
PATH_TO_SCHEDULES = "wnba/schedules/parquet"
PATH_TO_ROSTERS = "wnba/team_rosters/json"
MAX_THREADS = 8


def fetch_team_ids_for_season(season: int) -> list[int]:
    """Pull every team id ESPN exposes for a given WNBA season.

    Sources team ids from this season's WNBA schedule parquet (``home_id`` /
    ``away_id``). Falls back to the cached team-roster JSON directory if
    the schedule parquet is missing, then to ``sdv.wnba.espn_wnba_teams``.
    """
    schedule_path = Path(f"{PATH_TO_SCHEDULES}/wnba_schedule_{season}.parquet")
    if schedule_path.exists():
        df = pd.read_parquet(schedule_path)
        ids = pd.concat([df["home_id"], df["away_id"]], ignore_index=True)
        ids = pd.to_numeric(ids, errors="coerce").dropna().astype(int).unique().tolist()
        return sorted(ids)

    roster_dir = Path(f"{PATH_TO_ROSTERS}/{season}")
    if roster_dir.exists():
        ids = []
        for p in roster_dir.glob("*.json"):
            try:
                ids.append(int(p.stem))
            except (TypeError, ValueError):
                continue
        if ids:
            logger.warning(
                f"No schedule parquet at {schedule_path}; using cached roster ids "
                f"from {roster_dir}"
            )
            return sorted(set(ids))

    logger.warning(
        f"No schedule parquet at {schedule_path} and no cached rosters; "
        f"falling back to espn_wnba_teams()"
    )
    teams = sdv.wnba.espn_wnba_teams(return_as_pandas=True)
    return sorted(teams["team_id"].astype(int).tolist())


def download_team_stats_batch(
    season: int,
    team_ids: list[int],
    output_dir: Path,
    rerun_existing: bool,
    cores: int,
) -> None:
    threads = min(cores, max(1, len(team_ids)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futs = {
            executor.submit(
                download_team_stats, season, tid, output_dir, rerun_existing
            ): tid
            for tid in team_ids
        }
        for fut in tqdm(
            concurrent.futures.as_completed(futs),
            total=len(futs),
            desc=f"WNBA team stats {season}",
        ):
            fut.result()


def download_team_stats(
    season: int, team_id: int, output_dir: Path, rerun_existing: bool
) -> str:
    out_path = Path(output_dir) / f"{team_id}.json"
    if out_path.exists() and not rerun_existing:
        return f"skip {team_id}"
    try:
        raw: dict[str, Any] = espn_wnba_team_stats(
            team_id=int(team_id), season=int(season), raw=True
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=0, sort_keys=False)
        return f"ok {team_id}"
    except Exception as e:
        logger.warning(
            f"season={season} team_id={team_id} failed: {e!r}"
        )
        return f"err {team_id}: {e}"


def scrape_season(
    season: int, cores: int, rerun_existing: bool, base_output_dir: str
) -> None:
    output_dir = Path(f"{base_output_dir}/{season}")
    output_dir.mkdir(parents=True, exist_ok=True)
    team_ids = fetch_team_ids_for_season(season)
    logger.info(f"season={season} teams={len(team_ids)}")
    if not team_ids:
        logger.info(f"No team ids for {season}; skipping")
        return
    t0 = time.time()
    download_team_stats_batch(season, team_ids, output_dir, rerun_existing, cores)
    t1 = time.time()
    logger.info(
        f"{(t1 - t0) / 60:.2f} minutes to download {len(team_ids)} team-stat payloads for {season}."
    )


def main() -> None:
    if args.start_year < 1997:
        start_year = 1997
    else:
        start_year = args.start_year
    end_year = args.end_year if args.end_year is not None else start_year
    cores = args.cores if args.cores is not None else MAX_THREADS
    base_output_dir = args.output_dir or PATH_TO_OUTPUT
    rerun_existing = args.rerun_existing or args.force

    for season in range(start_year, end_year + 1):
        scrape_season(season, cores, rerun_existing, base_output_dir)

    gc.collect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start_year",
        "--start-year",
        "-s",
        dest="start_year",
        type=int,
        required=True,
        help="Start year of WNBA team-stats scrape (YYYY), e.g. 2025 for the 2025 season",
    )
    parser.add_argument(
        "--end_year",
        "--end-year",
        "-e",
        dest="end_year",
        type=int,
        help="End year of WNBA team-stats scrape (YYYY)",
    )
    parser.add_argument(
        "--cores",
        "--workers",
        "-c",
        dest="cores",
        type=int,
        default=MAX_THREADS,
        help="Concurrent worker threads (default 8).",
    )
    parser.add_argument(
        "--output-dir",
        "--output_dir",
        dest="output_dir",
        type=str,
        default=None,
        help=f"Override base output directory (default {PATH_TO_OUTPUT}).",
    )
    parser.add_argument(
        "--rerun_existing",
        "-r",
        nargs="?",
        const=True,
        default=False,
        type=lambda v: str(v).lower() in ("true", "1", "yes", "y", "t"),
        help="Re-scrape stats even when the output file already exists. Accepts a true/false value (e.g. `-r true`) for compat with the legacy umbrella workflow; bare `-r` defaults to True.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Alias for --rerun_existing.",
    )
    args = parser.parse_args()

    main()
