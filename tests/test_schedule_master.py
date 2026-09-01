"""Id canonicalization, per-season capture columns, and the master/coverage roll-up."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from sportsdataverse.scrape.espn.ids import to_int64, with_int64_ids
from sportsdataverse.scrape.espn.master import build_coverage, build_master
from sportsdataverse.scrape.espn.paths import raw_github_url
from sportsdataverse.scrape.espn.schedule import add_capture_columns

# --- ids ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "values,dtype",
    [
        ([401811123], pl.Int32),
        ([401811123], pl.Int64),
        (["401811123"], pl.Utf8),
        ([401811123.0], pl.Float64),
    ],
    ids=["int32", "int64", "utf8", "float64"],
)
def test_every_source_dtype_lands_on_int64(values, dtype):
    out = to_int64(pl.Series("game_id", values, dtype=dtype))
    assert out.dtype == pl.Int64
    assert out[0] == 401811123


def test_nulls_survive_canonicalization():
    out = to_int64(pl.Series("game_id", [None, 401811123], dtype=pl.Int64))
    assert out.null_count() == 1


def test_lossy_float_refuses_rather_than_truncating():
    with pytest.raises(ValueError, match="lossy"):
        to_int64(pl.Series("game_id", [401811123.5]))


def test_non_numeric_string_refuses():
    with pytest.raises(ValueError, match="non-numeric"):
        to_int64(pl.Series("game_id", ["not-an-id"]))


def test_with_int64_ids_skips_absent_columns():
    df = pl.DataFrame({"game_id": [1]}, schema={"game_id": pl.Int32})
    out = with_int64_ids(df, "game_id", "venue_id")
    assert out.schema["game_id"] == pl.Int64
    assert "venue_id" not in out.columns


# --- per-season capture columns ----------------------------------------------

NEW_COLUMNS = [
    "game_json_url",
    "game_json_raw_url",
    "game_rosters_json_url",
    "officials_json_url",
    "has_game_json",
    "has_game_rosters_json",
    "has_officials_json",
]


def _tree(tmp_path: Path) -> Path:
    for sub in (
        ("json", "final"),
        ("json", "raw"),
        ("game_rosters", "json"),
        ("officials", "json"),
    ):
        (tmp_path / "wnba" / Path(*sub)).mkdir(parents=True)
    (tmp_path / "wnba" / "json" / "final" / "401811123.json").write_text("{}")
    (tmp_path / "wnba" / "game_rosters" / "json" / "401811123.json").write_text("{}")
    return tmp_path


def _schedule() -> pl.DataFrame:
    return pl.DataFrame({"game_id": [401811123, 401811124]}, schema={"game_id": pl.Int32})


def test_adds_every_column(tmp_path):
    out = add_capture_columns(_schedule(), root=_tree(tmp_path), league="wnba")
    for column in NEW_COLUMNS:
        assert column in out.columns


def test_urls_emitted_for_every_row_even_when_the_file_is_absent(tmp_path):
    out = add_capture_columns(_schedule(), root=_tree(tmp_path), league="wnba")
    assert out["game_json_url"].null_count() == 0
    assert out["game_json_url"][1].endswith("wnba/json/final/401811124.json")


def test_has_flags_reflect_what_is_on_disk(tmp_path):
    out = add_capture_columns(_schedule(), root=_tree(tmp_path), league="wnba")
    assert out["has_game_json"].to_list() == [True, False]
    assert out["has_game_rosters_json"].to_list() == [True, False]
    assert out["has_officials_json"].to_list() == [False, False]


def test_game_id_is_canonicalized_to_int64(tmp_path):
    out = add_capture_columns(_schedule(), root=_tree(tmp_path), league="wnba")
    assert out.schema["game_id"] == pl.Int64


def test_url_never_contains_a_float_artifact(tmp_path):
    """A float-origin id stringifies as "123.0" and addresses nothing."""
    df = pl.DataFrame({"game_id": [401811123.0]})
    out = add_capture_columns(df, root=_tree(tmp_path), league="wnba")
    assert ".0.json" not in out["game_json_url"][0]
    assert out["game_json_url"][0].endswith("401811123.json")


def test_raw_github_url_shape():
    assert raw_github_url("wehoop-wnba-raw", "wnba", "json", "final", "1.json") == (
        "https://raw.githubusercontent.com/sportsdataverse/wehoop-wnba-raw/main/"
        "wnba/json/final/1.json"
    )


# --- master + coverage --------------------------------------------------------


def _season(season: int, n: int, captured: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_id": [900000 + season * 100 + i for i in range(n)],
            "season": [season] * n,
            "season_type": [2] * n,
            "date": ["2025-11-0%d" % (i % 9 + 1) for i in range(n)],
            "has_game_json": [i < captured for i in range(n)],
            "has_game_rosters_json": [False] * n,
            "has_officials_json": [False] * n,
        }
    )


def test_master_is_the_union_of_seasons():
    master = build_master([_season(2025, 4, 2), _season(2026, 6, 6)])
    assert master.height == 10
    assert set(master["season"].unique().to_list()) == {2025, 2026}


def test_master_pins_one_column_order_across_ragged_inputs():
    a = _season(2025, 2, 1)
    b = _season(2026, 2, 2).with_columns(pl.lit(1200).alias("venue_capacity"))
    assert build_master([a, b]).columns == build_master([b, a]).columns


def test_a_column_missing_from_one_season_is_null_filled():
    a = _season(2025, 2, 1)
    b = _season(2026, 2, 2).with_columns(pl.lit(1200).alias("venue_capacity"))
    master = build_master([a, b])
    assert master["venue_capacity"].null_count() == 2


def test_master_game_id_is_int64():
    assert build_master([_season(2026, 2, 2)]).schema["game_id"] == pl.Int64


def test_build_master_refuses_an_empty_input():
    with pytest.raises(ValueError, match="at least one"):
        build_master([])


def test_coverage_is_one_row_per_season_and_type():
    coverage = build_coverage(build_master([_season(2025, 4, 2), _season(2026, 6, 6)]))
    assert coverage.height == 2
    row = coverage.filter(pl.col("season") == 2025).to_dicts()[0]
    assert row["n_games"] == 4
    assert row["pct_json_captured"] == pytest.approx(0.5)


def test_coverage_has_a_pct_column_per_flag():
    coverage = build_coverage(build_master([_season(2026, 2, 1)]))
    for column in (
        "pct_has_game_json",
        "pct_has_game_rosters_json",
        "pct_has_officials_json",
    ):
        assert column in coverage.columns


def test_coverage_carries_the_date_range():
    coverage = build_coverage(build_master([_season(2026, 4, 4)]))
    row = coverage.to_dicts()[0]
    assert row["first_date"] <= row["last_date"]
