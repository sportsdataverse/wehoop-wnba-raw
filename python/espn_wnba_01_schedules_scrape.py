import argparse
import concurrent.futures
import gc
import logging
import os
import time
from itertools import repeat
from pathlib import Path

import pandas as pd
import polars as pl
import pyreadr
import sportsdataverse as sdv
from sportsdataverse.scrape.espn.cli import str2bool
from sportsdataverse.scrape.espn.ids import with_int64_ids

logging.basicConfig(level=logging.INFO, filename="wehoop_wnba_raw_logfile.txt")
logger = logging.getLogger(__name__)


path_to_schedules = "wnba/schedules"
final_file_name = "wnba/wnba_schedule_master.parquet"
MAX_THREADS = 30

# Published id dtype: Int64 for every `id` / `*_id` column of the schedule (id, type_id,
# status_type_id, game_id, home_id, away_id, venue_id, home_venue_id, away_venue_id,
# home_conference_id, away_conference_id, groups_id, tournament_id), whatever dtype sdv-py
# returns (String before its Int64 id contract, Int64 after it). The .rds gets R integer.
INT32_MAX = 2**31 - 1


def is_id_column(name: str) -> bool:
    return name == "id" or name.endswith("_id")


def _id_prep(df: pl.DataFrame, c: str) -> pl.Expr:
    dtype = df.schema[c]
    if dtype == pl.String:
        return pl.col(c).str.strip_chars().replace("", None)
    if dtype.is_float():
        return pl.col(c).fill_nan(None)
    return pl.col(c).cast(pl.Int64) if dtype == pl.Null else pl.col(c)


def cast_ids_int64(df: pl.DataFrame | pd.DataFrame, *, rds: bool = False):
    """Cast every id column to Int64, strictly; a pandas frame comes back pandas.

    Strings are stripped and ``""`` becomes null; a whole-number float is accepted and NaN
    becomes null. Anything else (``"abc"``, ``1.5``) raises ``ValueError`` instead of nulling.
    ``rds=True`` (pandas only) returns nullable ``Int32`` instead: pyreadr writes that as R
    integer with NA, and cannot write an ``Int64`` NA at all.
    """
    if isinstance(df, pd.DataFrame):
        out = df.copy()
        for c in filter(is_id_column, out.columns):
            col = cast_ids_int64(pl.DataFrame({c: pl.from_pandas(out[c])})).get_column(c)
            if rds and (col.abs() > INT32_MAX).any():  # Int64 -> Int32 would wrap silently
                raise ValueError(f"{c!r} exceeds the R integer range")
            out[c] = pd.array(col.to_list(), dtype="Int32" if rds else "Int64")
        return out
    cols = [c for c in df.columns if is_id_column(c)]
    return with_int64_ids(df.with_columns(_id_prep(df, c) for c in cols), *cols)


def download_game_schedules(seasons, path_to_schedules):
    threads = min(MAX_THREADS, len(seasons))

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
        result = list(executor.map(download_schedule, seasons, repeat(path_to_schedules)))
        return result


def download_schedule(season, path_to_schedules=None):
    logger.info(f"Scraping WNBA schedules for year {season}...")
    df = sdv.wnba.espn_wnba_calendar(season, ondays=True, return_as_pandas=True)

    calendar = df["dateURL"].str.replace("-", "").tolist()
    ev = pd.DataFrame()
    for d in calendar:
        date_schedule = sdv.wnba.espn_wnba_schedule(dates=d, return_as_pandas=True)
        ev = pd.concat([ev, date_schedule], axis=0, ignore_index=True)
    ev = ev[ev["season_type"].isin([2, 3])]

    ev = ev.drop_duplicates(subset=["game_id"], ignore_index=True)

    Path(f"{path_to_schedules}/parquet").mkdir(parents=True, exist_ok=True)
    Path(f"{path_to_schedules}/rds").mkdir(parents=True, exist_ok=True)
    if path_to_schedules is not None:
        ids = cast_ids_int64(ev)
        ids.to_parquet(f"{path_to_schedules}/parquet/wnba_schedule_{season}.parquet", index=False)
        rds = cast_ids_int64(ev, rds=True)
        pyreadr.write_rds(f"{path_to_schedules}/rds/wnba_schedule_{season}.rds", rds, compress="gzip")


def main():
    if args.start_year < 1997:
        start_year = 1997
    else:
        start_year = args.start_year
    if args.end_year is None:
        end_year = start_year
    else:
        end_year = args.end_year
    years_arr = range(start_year, end_year + 1)

    if args.rescrape == True:
        t0 = time.time()
        download_game_schedules(years_arr, path_to_schedules)
        t1 = time.time()
        logger.info(f"{(t1 - t0) / 60} minutes to download {len(years_arr)} years of season schedules.")

    parquet_files = [
        pos_parquet.replace(".parquet", "")
        for pos_parquet in os.listdir(path_to_schedules + "/parquet")
        if pos_parquet.endswith(".parquet")
    ]
    glued_data = pd.DataFrame()
    for index, js in enumerate(parquet_files):
        x = pd.read_parquet(f"{path_to_schedules}/parquet/{js}.parquet", engine="auto", columns=None)
        x = cast_ids_int64(x)  # every season Int64 before the concat, whatever wrote it
        glued_data = pd.concat([glued_data, x], axis=0)
    glued_data["status_display_clock"] = glued_data["status_display_clock"].astype(str)
    glued_data.to_parquet(final_file_name, index=False)
    gc.collect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start_year", "-s", type=int, required=True, help="Start year of WNBA Schedule period (YYYY)")
    parser.add_argument("--end_year", "-e", type=int, help="End year of WNBA Schedule period (YYYY)")
    parser.add_argument("--rescrape", "-r", type=str2bool, default=False, help="Rescrape all games in the schedule period")
    args = parser.parse_args()

    main()
