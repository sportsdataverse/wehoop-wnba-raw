
"""Scrape ESPN WNBA draft results per season.

Output: ``wnba/draft/json/{season}.json`` -- raw ESPN response. The
downstream R parser in ``wehoop-wnba-data`` reads these JSONs to build
the per-season tidy draft frame.

Draft is one HTTP call per season. The companion workflow
``.github/workflows/wehoop_wnba_draft_trigger.yml`` only fires the
downstream parser when ``wnba/draft/json/**`` actually changes, so this
scrape is intended to run on its own annual cadence rather than inside
the daily flow.

Requirements:
    Depends on the ``espn_wnba_draft`` helper added to
    ``sportsdataverse-py`` (sportsdataverse/wnba/wnba_draft.py). The
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
from sportsdataverse.wnba.wnba_draft import espn_wnba_draft


logging.basicConfig(
    level=logging.INFO,
    filename="wehoop_wnba_raw_draft_logfile.txt",
)
logger = logging.getLogger(__name__)

PATH_TO_OUTPUT = "wnba/draft/json"
DEFAULT_THREADS = 1


def download_draft(
    season: int, output_dir: Path, rerun_existing: bool
) -> str:
    out_path = Path(output_dir) / f"{season}.json"
    if out_path.exists() and not rerun_existing:
        return f"skip {season}"
    try:
        raw: dict[str, Any] = espn_wnba_draft(season=int(season), raw=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, sort_keys=False, default=str)
        return f"ok {season}"
    except Exception as e:
        logger.warning(f"season={season} failed: {e!r}")
        return f"err {season}: {e}"


def download_draft_batch(
    seasons: list[int],
    output_dir: Path,
    rerun_existing: bool,
    cores: int,
) -> None:
    threads = min(cores, max(1, len(seasons)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futs = {
            executor.submit(
                download_draft, s, output_dir, rerun_existing
            ): s
            for s in seasons
        }
        for fut in tqdm(
            concurrent.futures.as_completed(futs),
            total=len(futs),
            desc="WNBA draft",
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
    download_draft_batch(seasons, base_output_dir, rerun_existing, cores)
    t1 = time.time()
    logger.info(
        f"{(t1 - t0) / 60:.2f} minutes to download {len(seasons)} draft payloads."
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
        help="Start year of WNBA draft scrape (YYYY)",
    )
    parser.add_argument(
        "--end_year",
        "--end-year",
        "-e",
        dest="end_year",
        type=int,
        help="End year of WNBA draft scrape (YYYY)",
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
        nargs="?",
        const=True,
        default=False,
        type=lambda v: str(v).lower() in ("true", "1", "yes", "y", "t"),
        help="Re-scrape draft results even when the output file already exists. Accepts a true/false value (e.g. `-r true`) for compat with the legacy umbrella workflow; bare `-r` defaults to True.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Alias for --rerun_existing.",
    )
    args = parser.parse_args()

    main()
