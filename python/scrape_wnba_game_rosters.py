
"""Scrape ESPN WNBA per-game rosters.

Output: ``wnba/game_rosters/json/{game_id}.json`` -- raw ESPN response.
The downstream R parser in ``wehoop-wnba-data`` reads these JSONs to
build the per-game tidy roster frame (one row per athlete-team-game).

Game ids are sourced from the season's schedule parquet
(``wnba/schedules/parquet/wnba_schedule_{year}.parquet``). If the parquet
is missing, falls back to a fresh ``sdv.wnba.espn_wnba_schedule`` call.

Requirements:
    Depends on the ``espn_wnba_game_rosters`` helper added to
    ``sportsdataverse-py`` (sportsdataverse/wnba/wnba_game_rosters.py). The
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
from sportsdataverse.wnba.wnba_game_rosters import espn_wnba_game_rosters


logging.basicConfig(
    level=logging.INFO,
    filename="wehoop_wnba_raw_game_rosters_logfile.txt",
)
logger = logging.getLogger(__name__)

PATH_TO_OUTPUT = "wnba/game_rosters/json"
PATH_TO_SCHEDULES = "wnba/schedules/parquet"
MAX_THREADS = 8


def fetch_game_ids_for_season(season: int) -> list[int]:
    """Pull every completed game id ESPN exposes for a given WNBA season.

    Reads from the season's schedule parquet first (the canonical source
    used by every other per-game scraper in this repo). Falls back to a
    fresh ``espn_wnba_schedule`` call when the parquet is missing.
    """
    schedule_path = Path(f"{PATH_TO_SCHEDULES}/wnba_schedule_{season}.parquet")
    if schedule_path.exists():
        df = pd.read_parquet(schedule_path)
        if "status_type_completed" in df.columns:
            df = df[df["status_type_completed"] == True]  # noqa: E712
        ids = pd.to_numeric(df["game_id"], errors="coerce").dropna().astype(int)
        return sorted(ids.unique().tolist())

    logger.warning(
        f"No schedule parquet at {schedule_path}; falling back to espn_wnba_schedule()"
    )
    sched = sdv.wnba.espn_wnba_schedule(season=season)
    if hasattr(sched, "to_pandas"):
        sched = sched.to_pandas()
    if "status_type_completed" in sched.columns:
        sched = sched[sched["status_type_completed"] == True]  # noqa: E712
    ids = pd.to_numeric(sched["game_id"], errors="coerce").dropna().astype(int)
    return sorted(ids.unique().tolist())


def download_game_rosters_batch(
    season: int,
    game_ids: list[int],
    output_dir: Path,
    rerun_existing: bool,
    cores: int,
) -> None:
    threads = min(cores, max(1, len(game_ids)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futs = {
            executor.submit(
                download_game_rosters, gid, output_dir, rerun_existing
            ): gid
            for gid in game_ids
        }
        for fut in tqdm(
            concurrent.futures.as_completed(futs),
            total=len(futs),
            desc=f"WNBA game rosters {season}",
        ):
            fut.result()


def download_game_rosters(
    game_id: int, output_dir: Path, rerun_existing: bool
) -> str:
    out_path = Path(output_dir) / f"{game_id}.json"
    if out_path.exists() and not rerun_existing:
        return f"skip {game_id}"
    try:
        raw: dict[str, Any] = espn_wnba_game_rosters(game_id=int(game_id), raw=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=0, sort_keys=False, default=str)
        return f"ok {game_id}"
    except Exception as e:
        # Per-game tolerance: 404s, schema drift, transient ESPN failures
        # must NOT abort the season's run.
        logger.warning(f"game_id={game_id} failed: {e!r}")
        return f"err {game_id}: {e}"


def scrape_season(
    season: int, cores: int, rerun_existing: bool, base_output_dir: str
) -> None:
    output_dir = Path(base_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    game_ids = fetch_game_ids_for_season(season)
    logger.info(f"season={season} games={len(game_ids)}")
    if not game_ids:
        logger.info(f"No game ids for {season}; skipping")
        return
    t0 = time.time()
    download_game_rosters_batch(
        season, game_ids, output_dir, rerun_existing, cores
    )
    t1 = time.time()
    logger.info(
        f"{(t1 - t0) / 60:.2f} minutes to download {len(game_ids)} game rosters for {season}."
    )


def main() -> None:
    if args.start_year < 2002:
        start_year = 2002
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
        help="Start year of WNBA game-roster scrape (YYYY), e.g. 2025",
    )
    parser.add_argument(
        "--end_year",
        "--end-year",
        "-e",
        dest="end_year",
        type=int,
        help="End year of WNBA game-roster scrape (YYYY)",
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
        help="Re-scrape rosters even when the output file already exists. Accepts a true/false value (e.g. `-r true`) for compat with the legacy umbrella workflow; bare `-r` defaults to True.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Alias for --rerun_existing.",
    )
    args = parser.parse_args()

    main()
