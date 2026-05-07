
"""Scrape ESPN WNBA standings per season.

Output: ``wnba/standings/json/{season}.json`` -- raw ESPN response. The
downstream R parser in ``wehoop-wnba-data`` reads these JSONs to build
the per-season tidy standings frame.

Standings is one HTTP call per season -- there is no per-team iteration,
so concurrency only helps when scraping a multi-season backfill.

Requirements:
    Depends on the ``espn_wnba_standings`` helper added to
    ``sportsdataverse-py`` (sportsdataverse/wnba/wnba_standings.py). The
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

from tqdm import tqdm

# The new module is not yet re-exported from ``sportsdataverse.wnba``, so we
# import the function directly from its module to avoid relying on the
# top-level package surface.
from sportsdataverse.wnba.wnba_standings import espn_wnba_standings


logging.basicConfig(
    level=logging.INFO,
    filename="wehoop_wnba_raw_standings_logfile.txt",
)
logger = logging.getLogger(__name__)

PATH_TO_OUTPUT = "wnba/standings/json"
DEFAULT_THREADS = 1


def download_standings(
    season: int, output_dir: Path, rerun_existing: bool
) -> str:
    out_path = Path(output_dir) / f"{season}.json"
    if out_path.exists() and not rerun_existing:
        return f"skip {season}"
    try:
        raw: dict[str, Any] = espn_wnba_standings(season=int(season), raw=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, sort_keys=False, default=str)
        return f"ok {season}"
    except Exception as e:
        logger.warning(f"season={season} failed: {e!r}")
        return f"err {season}: {e}"


def download_standings_batch(
    seasons: list[int],
    output_dir: Path,
    rerun_existing: bool,
    cores: int,
) -> None:
    threads = min(cores, max(1, len(seasons)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futs = {
            executor.submit(
                download_standings, s, output_dir, rerun_existing
            ): s
            for s in seasons
        }
        for fut in tqdm(
            concurrent.futures.as_completed(futs),
            total=len(futs),
            desc="WNBA standings",
        ):
            fut.result()


def main() -> None:
    if args.start_year < 1997:
        start_year = 1997
    else:
        start_year = args.start_year
    end_year = args.end_year if args.end_year is not None else start_year
    cores = args.cores if args.cores is not None else DEFAULT_THREADS
    base_output_dir = Path(args.output_dir or PATH_TO_OUTPUT)
    base_output_dir.mkdir(parents=True, exist_ok=True)
    rerun_existing = args.rerun_existing or args.force

    seasons = list(range(start_year, end_year + 1))
    logger.info(f"seasons={seasons}")
    if not seasons:
        return
    t0 = time.time()
    download_standings_batch(seasons, base_output_dir, rerun_existing, cores)
    t1 = time.time()
    logger.info(
        f"{(t1 - t0) / 60:.2f} minutes to download {len(seasons)} standings payloads."
    )

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
        help="Start year of WNBA standings scrape (YYYY), e.g. 2025 for the 2025 season",
    )
    parser.add_argument(
        "--end_year",
        "--end-year",
        "-e",
        dest="end_year",
        type=int,
        help="End year of WNBA standings scrape (YYYY)",
    )
    parser.add_argument(
        "--cores",
        "--workers",
        "-c",
        dest="cores",
        type=int,
        default=DEFAULT_THREADS,
        help="Concurrent worker threads (default 1 -- one HTTP call per season).",
    )
    parser.add_argument(
        "--output-dir",
        "--output_dir",
        dest="output_dir",
        type=str,
        default=None,
        help=f"Override output directory (default {PATH_TO_OUTPUT}).",
    )
    parser.add_argument(
        "--rerun_existing",
        "-r",
        action="store_true",
        help="Re-scrape standings even when the output file already exists.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Alias for --rerun_existing.",
    )
    args = parser.parse_args()

    main()
