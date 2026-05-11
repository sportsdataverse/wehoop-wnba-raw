
"""Scrape ESPN WNBA athlete season stats.

Output: ``wnba/player_season_stats/json/{season}/{athlete_id}.json`` --
raw ESPN response. The downstream R parser in ``wehoop-wnba-data`` reads
these JSONs to build the per-season tidy player-stats frame.

Athlete ids are sourced from the rosters JSONs produced by
``scrape_wnba_team_rosters.py`` -- run that script first for the same
``--start_year``/``--end_year`` window.

Requirements:
    Depends on the ``espn_wnba_player_stats`` helper added to
    ``sportsdataverse-py`` (sportsdataverse/wnba/wnba_player_stats.py).
"""

import argparse
import concurrent.futures
import gc
import json
import logging
import time
from pathlib import Path

from tqdm import tqdm

# Imported direct from the module path because the new helpers are not yet
# re-exported via sportsdataverse.wnba.__init__.
from sportsdataverse.wnba.wnba_player_stats import espn_wnba_player_stats


logging.basicConfig(
    level=logging.INFO,
    filename="wehoop_wnba_raw_player_stats_logfile.txt",
)
logger = logging.getLogger(__name__)

PATH_TO_OUTPUT = "wnba/player_season_stats/json"
PATH_TO_ROSTERS = "wnba/team_rosters/json"
# Player stats endpoint is per-athlete; ESPN rate-limits more aggressively
# here than on the per-team roster endpoint, so default cores is lower.
DEFAULT_THREADS = 4


def _athlete_ids_from_roster(payload):
    """Extract integer athlete ids from one ESPN team-roster response.

    Handles the two shapes ESPN ships:
      * ``athletes`` is a flat list of athlete dicts; pull ``id`` directly.
      * ``athletes`` is a list of position-group buckets each carrying an
        ``items`` array; flatten then pull ``id``.
    """
    raw = payload.get("athletes") if isinstance(payload, dict) else None
    if not isinstance(raw, list) or not raw:
        return []

    if isinstance(raw[0], dict) and "items" in raw[0]:
        athletes = []
        for group in raw:
            items = group.get("items") or []
            if isinstance(items, list):
                athletes.extend(a for a in items if isinstance(a, dict))
    else:
        athletes = [a for a in raw if isinstance(a, dict)]

    ids = []
    for a in athletes:
        aid = a.get("id")
        if aid is None:
            continue
        try:
            ids.append(int(aid))
        except (TypeError, ValueError):
            continue
    return ids


def fetch_athlete_ids_for_season(season):
    """Walk ``team_rosters/json/{season}/*.json`` and collect unique athlete ids."""
    season_dir = Path(f"{PATH_TO_ROSTERS}/{season}")
    if not season_dir.exists():
        logger.warning(
            f"No rosters at {season_dir}; run scrape_wnba_team_rosters.py first."
        )
        return []

    seen = set()
    for roster_path in sorted(season_dir.glob("*.json")):
        try:
            with open(roster_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read {roster_path}: {e!r}")
            continue
        for aid in _athlete_ids_from_roster(payload):
            seen.add(aid)
    return sorted(seen)


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
        raw = espn_wnba_player_stats(
            athlete_id=int(athlete_id), season=int(season), raw=True
        )
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=0, sort_keys=False)
        return f"ok {athlete_id}"
    except Exception as e:
        logger.warning(
            f"season={season} athlete_id={athlete_id} failed: {e!r}"
        )
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
