"""Scrape ESPN WNBA athlete season stats.

Output: ``wnba/player_season_stats/json/{season}/{athlete_id}.json`` --
raw ESPN response. The downstream R parser in ``wehoop-wnba-data`` reads
these JSONs to build the per-season tidy player-stats frame.

Athlete ids are sourced from the ``espn_wnba_player_boxscores`` release on
sportsdataverse-data -- the union of every athlete who appeared in a box
score that season. ESPN's ``/teams/{id}/roster`` endpoint ignores the
season query param and only ever returns the *current* roster, so it
cannot supply historical rosters; the box-score release is the
authoritative "who played in season Y" list and covers every season back
to 2002.

Requirements:
    Depends on the ``espn_wnba_player_stats`` helper added to
    ``sportsdataverse-py`` (sportsdataverse/wnba/wnba_player_stats.py).
"""

import argparse
import concurrent.futures
import gc
import io
import json
import logging
import time
from pathlib import Path

from tqdm import tqdm

# Imported direct from the module path because the new helpers are not yet
# re-exported via sportsdataverse.wnba.__init__.
# _v3 == the site.web.api common/v3 .../athletes/{id}/stats CAREER endpoint,
# which is what every file under wnba/player_season_stats/json/ is and what the
# downstream parser reads (categories[].statistics[]). The unsuffixed
# espn_wnba_player_stats is core-v2 /athletes/{id}/statistics -- a DIFFERENT
# API returning $ref/season/athlete/splits. It imports fine and fails silently,
# so do not "simplify" this import.
from sportsdataverse.wnba import espn_wnba_player_stats_v3
from sportsdataverse.dl_utils import download


logging.basicConfig(
    level=logging.INFO,
    filename="wehoop_wnba_raw_player_stats_logfile.txt",
)
logger = logging.getLogger(__name__)

PATH_TO_OUTPUT = "wnba/player_season_stats/json"
PLAYER_BOX_RELEASE = (
    "https://github.com/sportsdataverse/sportsdataverse-data/releases/"
    "download/espn_wnba_player_boxscores/player_box_{season}.parquet"
)
# Player stats endpoint is per-athlete; ESPN rate-limits more aggressively
# here than on the per-team roster endpoint, so default cores is lower.
DEFAULT_THREADS = 4


def fetch_athlete_ids_for_season(season):
    """Read the espn_wnba_player_boxscores release parquet for ``season``
    and return the unique integer athlete ids that appeared that year.

    Never raises -- on any failure (network, missing release asset, schema
    drift) logs a warning and returns ``[]`` so one bad season can't abort
    a multi-season run.
    """
    url = PLAYER_BOX_RELEASE.format(season=int(season))
    try:
        import pandas as pd

        resp = download(url)
        content = resp.content if hasattr(resp, "content") else resp
        df = pd.read_parquet(io.BytesIO(content), columns=["athlete_id"])
        ids = sorted(
            {
                int(x)
                for x in df["athlete_id"].dropna().unique()
                if str(x).strip().isdigit() or isinstance(x, (int, float))
            }
        )
        return ids
    except Exception as e:  # noqa: BLE001
        logger.warning(f"could not list player_box athletes for {season}: {e!r}")
        return []


def download_player_stats_batch(season, athlete_ids, output_dir, rerun_existing, cores):
    threads = min(cores, max(1, len(athlete_ids)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        futs = {
            executor.submit(
                download_player_stats, season, aid, output_dir, rerun_existing
            ): aid
            for aid in athlete_ids
        }
        for fut in tqdm(
            concurrent.futures.as_completed(futs),
            total=len(futs),
            desc=f"WNBA player stats {season}",
        ):
            fut.result()


def download_player_stats(season, athlete_id, output_dir, rerun_existing):
    out_path = Path(output_dir) / f"{athlete_id}.json"
    if out_path.exists() and not rerun_existing:
        return f"skip {athlete_id}"
    try:
        raw = espn_wnba_player_stats_v3(
            athlete_id=int(athlete_id), season=int(season), return_parsed=False
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=0, sort_keys=False)
        return f"ok {athlete_id}"
    except Exception as e:
        logger.warning(f"season={season} athlete_id={athlete_id} failed: {e!r}")
        return f"err {athlete_id}: {e}"


def scrape_season(season, cores, rerun_existing):
    output_dir = Path(f"{PATH_TO_OUTPUT}/{season}")
    output_dir.mkdir(parents=True, exist_ok=True)
    athlete_ids = fetch_athlete_ids_for_season(season)
    logger.info(f"season={season} athletes={len(athlete_ids)}")
    if not athlete_ids:
        logger.info(f"No athlete ids for {season}; skipping")
        return
    t0 = time.time()
    download_player_stats_batch(season, athlete_ids, output_dir, rerun_existing, cores)
    t1 = time.time()
    logger.info(
        f"{(t1 - t0) / 60:.2f} minutes to download {len(athlete_ids)} player-stat payloads for {season}."
    )


def main():
    if args.start_year < 1997:
        start_year = 1997
    else:
        start_year = args.start_year
    end_year = args.end_year if args.end_year is not None else start_year
    cores = args.cores if args.cores is not None else DEFAULT_THREADS

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
        help="Start year of WNBA player-stats scrape (YYYY)",
    )
    parser.add_argument(
        "--end_year",
        "-e",
        type=int,
        help="End year of WNBA player-stats scrape (YYYY)",
    )
    parser.add_argument(
        "--cores",
        "-c",
        type=int,
        default=DEFAULT_THREADS,
        help="Concurrent worker threads (default 4 -- ESPN rate-limits per-athlete more aggressively).",
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
    args = parser.parse_args()

    main()
