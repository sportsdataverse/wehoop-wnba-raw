"""One-off: reprocess pre-2006 WNBA final.json from the stored raw captures.

Incident: sportsdataverse-py #380 fixed the hard-coded quarters model for
pre-2006 WNBA games (2x20-minute halves; wehoop#39). The scraper bakes the
processed payload into ``wnba/json/final`` at capture time, so every
pre-2006 final.json carries wrong half / seconds-remaining / OT columns.
The raw allowlisted summaries in ``wnba/json/raw`` (which include the
authoritative ``format.regulation.periods``) allow a fully offline rebuild:

    uv run python ops/oneoff/2026-08-23_reprocess_pre2006_halves.py -s 2002 -e 2005

Run AFTER re-locking sportsdataverse to current main (the fix merged
2026-08-23). Idempotent; --dry-run reports without writing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import sportsdataverse as sdv

RAW_DIR = Path("wnba/json/raw")
FINAL_DIR = Path("wnba/json/final")
SCHED_DIR = Path("wnba/schedules/parquet")


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def season_game_ids(season: int) -> list[int]:
    df = pd.read_parquet(SCHED_DIR / f"wnba_schedule_{season}.parquet")
    if "status_type_completed" in df.columns:
        df = df[df["status_type_completed"] == True]  # noqa: E712
    return sorted(int(g) for g in df["game_id"].unique())


def validate_halves(final: dict, game_id: int) -> list[str]:
    """Era invariants for a halves-era processed payload; [] when clean."""
    plays = final.get("plays") or []
    if not plays:
        return []
    errs = []
    p1 = [p for p in plays if p.get("period.number") == 1]
    p2 = [p for p in plays if p.get("period.number") == 2]
    if p1 and {p.get("half") for p in p1} != {1}:
        errs.append("p1 half != 1")
    if p2 and {p.get("half") for p in p2} != {2}:
        errs.append("p2 half != 2 (quarters model leaked)")
    gsr2 = [p.get("start.game_seconds_remaining") for p in p2]
    gsr2 = [v for v in gsr2 if v is not None]
    if gsr2 and max(gsr2) > 1200:
        errs.append(f"p2 game_seconds max {max(gsr2)} > 1200")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--start", type=int, default=2002)
    ap.add_argument("-e", "--end", type=int, default=2005)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    total = ok = missing = failed = bad = 0
    for season in range(a.start, a.end + 1):
        ids = season_game_ids(season)
        log(f"season {season}: {len(ids)} completed games")
        for gid in ids:
            total += 1
            if not (RAW_DIR / f"{gid}.json").exists():
                missing += 1
                continue
            try:
                pbp_txt = sdv.wnba.wnba_pbp_disk(game_id=gid, path_to_json=str(RAW_DIR))
                result = sdv.wnba.helper_wnba_pbp(game_id=gid, pbp_txt=pbp_txt)
            except Exception as e:  # noqa: BLE001 - per-game isolation, log + continue
                failed += 1
                log(f"FAIL {season} {gid}: {type(e).__name__}: {e}")
                continue
            errs = validate_halves(result, gid)
            if errs:
                bad += 1
                log(f"INVARIANT {season} {gid}: {'; '.join(errs)}")
                continue
            if not a.dry_run:
                with open(FINAL_DIR / f"{gid}.json", "w") as f:
                    json.dump(result, f, indent=0, sort_keys=False)
            ok += 1
        log(
            f"season {season} done (cumulative ok={ok} fail={failed} bad={bad} missing_raw={missing})"
        )
    log(
        f"REPROCESS_DONE total={total} ok={ok} fail={failed} invariant_bad={bad} missing_raw={missing}"
    )
    return 0 if failed == 0 and bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
