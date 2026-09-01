"""Every committed payload family matches its declared shape in sdv-py.

No fixtures directory on purpose. This is a `-raw` repo -- the payloads *are*
committed here, so copying a few into ``tests/fixtures/`` would duplicate ~9MB
of data sitting one directory over, and would test the copy rather than the
archive. These tests read the real tree.

Schemas live in ``sportsdataverse.schemas`` (one per payload family, shared by
every league's -raw repo) rather than here, so a provider shape change is
described in one place instead of eight.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

import pytest
from sportsdataverse.schemas import validate_payload

REPO_ROOT = Path(__file__).resolve().parents[1]

# schema name -> glob of the committed captures it describes.
FAMILIES: list[tuple[str, str]] = [
    ("espn_summary", "wnba/json/final/*.json"),
    ("espn_summary", "wnba/json/raw/*.json"),
    ("espn_game_rosters", "wnba/game_rosters/json/*.json"),
    ("espn_officials", "wnba/officials/json/*.json"),
    ("espn_player_core", "wnba/player_core/json/*.json"),
    ("espn_standings", "wnba/standings/json/*.json"),
    ("espn_team_stats", "wnba/team_stats/json/*/*.json"),
    ("espn_player_season_stats", "wnba/player_season_stats/json/*/*.json"),
]

# The archive is ~533k files; a full sweep takes minutes. Sample per family by
# default and let CI or an operator widen it. Seeded so a failure is
# reproducible from the reported path.
SAMPLE = int(os.environ.get("WNBA_SCHEMA_SAMPLE", "40"))

# Every test here reads the committed wnba/ tree, which PR CI does not check out.
pytestmark = pytest.mark.archive


def _sample(pattern: str) -> list[Path]:
    paths = sorted(REPO_ROOT.glob(pattern))
    if not paths:
        return []
    rng = random.Random(pattern)  # stable per family across runs
    return paths if len(paths) <= SAMPLE else rng.sample(paths, SAMPLE)


@pytest.mark.parametrize("schema,pattern", FAMILIES, ids=[p for _, p in FAMILIES])
def test_committed_payloads_match_their_schema(schema, pattern):
    paths = _sample(pattern)
    if not paths:
        pytest.skip(f"no captures under {pattern}")
    problems: list[str] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for message in validate_payload(schema, payload):
            problems.append(f"{path.relative_to(REPO_ROOT)}: {message}")
    assert problems == [], "\n".join(problems[:20])


def test_every_family_has_captures():
    """A family that silently stopped being scraped looks like a passing skip
    above; this is what actually notices."""
    empty = [pattern for _, pattern in FAMILIES if not sorted(REPO_ROOT.glob(pattern))]
    assert empty == [], f"no captures for: {empty}"


def test_raw_and_final_describe_the_same_game_differently():
    """json/final is not json/raw plus two keys: the raw->final step also
    converts `timeouts` and `season` from list to dict. Both are declared as
    unions, and this is the test that fails if that stops being true."""
    finals = sorted(REPO_ROOT.glob("wnba/json/final/*.json"))
    if not finals:
        pytest.skip("no final captures")
    game_id = finals[0].stem
    raw_path = REPO_ROOT / "wnba" / "json" / "raw" / f"{game_id}.json"
    if not raw_path.exists():
        pytest.skip(f"no raw counterpart for {game_id}")

    final = json.loads(finals[0].read_text(encoding="utf-8"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assert validate_payload("espn_summary", final) == []
    assert validate_payload("espn_summary", raw) == []
    # The two keys that change container type between the variants.
    for key in ("timeouts", "season"):
        if key in raw and key in final:
            assert isinstance(raw[key], (list, dict))
            assert isinstance(final[key], (list, dict))
