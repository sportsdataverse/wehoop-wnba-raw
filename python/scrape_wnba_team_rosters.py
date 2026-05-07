
"""Scrape ESPN WNBA team rosters per (season, team_id).

Output: ``wnba/team_rosters/json/{season}/{team_id}.json`` -- raw ESPN
response. The downstream R parser in ``wehoop-wnba-data`` reads these
JSONs to build the per-season tidy roster frame.

Requirements:
    Depends on the ``espn_wnba_team_roster`` helper added to
    ``sportsdataverse-py`` (sportsdataverse/wnba/wnba_team_roster.py). The
    repo's ``requirements.txt`` should pin a version of sportsdataverse-py
    that exports it; until that release lands, install sdv-py from source
    (``pip install -e <path>/sdv-py``).
"""

import argparse
import concurrent.futures
import gc
import json
import logging
import time
from pathlib import Path

import pandas as pd
import sportsdataverse as sdv
from tqdm import tqdm

# The new module is not yet re-exported from ``sportsdataverse.wnba``, so we
# import the function directly from its module to avoid relying on the
# top-level package surface.
from sportsdataverse.wnba.wnba_team_roster import espn_wnba_team_roster


logging.basicConfig(
    level=logging.INFO,
    filename="wehoop_wnba_raw_team_rosters_logfile.txt",
)
logger = logging.getLogger(__name__)

PATH_TO_OUTPUT = "wnba/team_rosters/json"
PATH_TO_SCHEDULES = "wnba/schedules/parquet"
MAX_THREADS = 8


def fetch_team_ids_for_season(season):
    """Pull every team id ESPN exposes for a given season.

    Sources team ids from this season's WNBA schedule parquet (``home_id`` /
    ``away_id``). Falls back to ``sdv.wnba.espn_wnba_teams`` if the
    schedule parquet is missing.
    """
    schedule_path = Path(f"{PATH_TO_SCHEDULES}/wnba_schedule_{season}.parquet")
    if schedule_path.exists():
        df = pd.read_parquet(schedule_path)
        ids = pd.concat([df["home_id"], df["away_id"]], ignore_index=True)
        ids = pd.to_numeric(ids, errors="coerce").dropna().astype(int).unique().tolist()
        return sorted(ids)

    logger.warning(
        f"No schedule parquet at {schedule_path}; falling back to espn_wnba_teams()"
    )
    teams = sdv.wnba.espn_wnba_teams(return_as_pandas=True)
    return sorted(teams["team_id"].astype(int).tolist())


def download_team_rosters(season, team_ids, output_dir, rerun_existing):
    threads = min(MAX_THREADS, max(1, len(team_ids)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futs = {
            executor.submit(
                download_team_roster, season, tid, output_dir, rerun_existing
            ): tid
            for tid in team_ids
        }
        for fut in tqdm(
            concurrent.futures.as_completed(futs),
            total=len(futs),
            desc=f"WNBA rosters {season}",
        ):
            fut.result()


def download_team_roster(season, team_id, output_dir, rerun_existing):
    out_path = Path(output_dir) / f"{team_id}.json"
    if out_path.exists() and not rerun_existing:
        return f"skip {team_id}"
    try:
        raw = espn_wnba_team_roster(team_id=int(team_id), season=int(season), raw=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=0, sort_keys=False, default=str)
        return f"ok {team_id}"
    except Exception as e:
        logger.warning(
            f"season={season} team_id={team_id} failed: {e!r}"
        )
        return f"err {team_id}: {e}"


def scrape_season(season, cores, rerun_existing):
    output_dir = Path(f"{PATH_TO_OUTPUT}/{season}")
    output_dir.mkdir(parents=True, exist_ok=True)
    team_ids = fetch_team_ids_for_season(season)
    logger.info(f"season={season} teams={len(team_ids)}")
    if not team_ids:
        logger.info(f"No team ids for {season}; skipping")
        return
    t0 = time.time()
    download_team_rosters(season, team_ids, output_dir, rerun_existing)
    t1 = time.time()
    logger.info(
        f"{(t1 - t0) / 60:.2f} minutes to download {len(team_ids)} team rosters for {season}."
    )


def main():
    if args.start_year < 1997:
        start_year = 1997
    else:
        start_year = args.start_year
    end_year = args.end_year if args.end_year is not None else start_year
    cores = args.cores if args.cores is not None else MAX_THREADS

    for season in range(start_year, end_year + 1):
        scrape_season(season, cores, args.rerun_existing)

    gc.collect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--start_year",
        "-s",
        type=int,
        required=True,
        help="Start year of WNBA roster scrape (YYYY), e.g. 2025 for the 2025 season",
    )
    parser.add_argument(
        "--end_year",
        "-e",
        type=int,
        help="End year of WNBA roster scrape (YYYY)",
    )
    parser.add_argument(
        "--cores",
        "-c",
        type=int,
        default=MAX_THREADS,
        help="Concurrent worker threads (default 8).",
    )
    parser.add_argument(
        "--rerun_existing",
        "-r",
        action="store_true",
        help="Re-scrape rosters even when the output file already exists.",
    )
    args = parser.parse_args()

    main()
