"""The archive must never contain a provider error body.

The raw tree is the scrape checkpoint: a captured file is never re-fetched. So
a persisted error body is permanent -- it silently yields an empty dataset for
that key on every rebuild, forever, with nothing failing anywhere.

Seven such files were found in ``wnba/team_stats/json/`` when the sdv-py payload
schemas were first run against the committed tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sportsdataverse.scrape.espn.persist import (
    is_error_payload,
    scan_for_error_payloads,
    write_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

# Both shapes observed in the committed archive.
SPRING_ERROR = {
    "error": "Not Found",
    "message": "",
    "path": "/apis/site/v2/...",
    "status": 404,
    "timestamp": "2026-01-01T00:00:00Z",
}
ESPN_ERROR = {"code": 404, "detail": "no data"}
GOOD = {"results": {"stats": []}, "team": {"id": "52"}}


@pytest.mark.parametrize(
    "payload",
    [SPRING_ERROR, ESPN_ERROR, {}, [], None, ""],
    ids=["spring", "espn", "empty-dict", "list", "none", "empty-str"],
)
def test_error_and_empty_payloads_are_recognized(payload):
    assert is_error_payload(payload) is True


@pytest.mark.parametrize(
    "payload",
    [GOOD, {"items": [], "count": 0}, {"categories": [], "teams": {}}],
    ids=["team_stats", "officials-envelope", "player_season_stats"],
)
def test_real_payloads_are_not_errors(payload):
    assert is_error_payload(payload) is False


def test_an_empty_but_valid_collection_is_not_an_error():
    """A zero-row Core v2 page is a real answer: this team had no officials.
    Treating it as an error would re-scrape it forever."""
    assert is_error_payload({"count": 0, "items": [], "pageCount": 0}) is False


def test_write_refuses_an_error_payload(tmp_path):
    path = tmp_path / "2948.json"
    assert write_payload(path, ESPN_ERROR) is False
    assert not path.exists()


def test_write_persists_a_real_payload(tmp_path):
    path = tmp_path / "52.json"
    assert write_payload(path, GOOD) is True
    assert json.loads(path.read_text(encoding="utf-8")) == GOOD


def test_write_creates_missing_parents(tmp_path):
    path = tmp_path / "2026" / "52.json"
    assert write_payload(path, GOOD) is True
    assert path.exists()


def test_write_never_truncates_a_good_file_with_a_bad_one(tmp_path):
    """The failure that actually matters: a good capture overwritten later by
    an error response, turning a working season into a silent gap."""
    path = tmp_path / "52.json"
    write_payload(path, GOOD)
    assert write_payload(path, SPRING_ERROR) is False
    assert json.loads(path.read_text(encoding="utf-8")) == GOOD


def test_scan_finds_error_payloads(tmp_path):
    (tmp_path / "2007").mkdir()
    (tmp_path / "2007" / "2948.json").write_text(json.dumps(ESPN_ERROR), encoding="utf-8")
    (tmp_path / "2007" / "52.json").write_text(json.dumps(GOOD), encoding="utf-8")
    found = scan_for_error_payloads(tmp_path, "*/*.json")
    assert [p.name for p in found] == ["2948.json"]


def test_scan_reports_unreadable_files(tmp_path):
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert [p.name for p in scan_for_error_payloads(tmp_path, "*.json")] == ["broken.json"]


# --- the archive itself ------------------------------------------------------


@pytest.mark.archive
@pytest.mark.parametrize(
    "pattern",
    [
        "wnba/team_stats/json/*/*.json",
        "wnba/officials/json/*.json",
        "wnba/standings/json/*.json",
        "wnba/player_season_stats/json/*/*.json",
    ],
)
def test_no_error_payloads_committed(pattern):
    """Guards the whole committed archive, not just fixtures. A persisted error
    body is a permanent, silent dataset gap."""
    bad = scan_for_error_payloads(REPO_ROOT, pattern)
    rel = [str(p.relative_to(REPO_ROOT)) for p in bad]
    assert rel == [], f"{len(rel)} error payloads committed: {rel[:10]}"
