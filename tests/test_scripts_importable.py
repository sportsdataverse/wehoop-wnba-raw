"""Every numbered scraper must import and answer --help.

This is the guard that would have caught two real defects in this repo:

* ``process_wnba_schedules.py`` imported ``schedule_handler``, a module that
  existed nowhere -- not tracked, not on disk, not in sportsdataverse. The
  script could never run, and nothing said so.
* Dropping ``requirements.txt`` for a hand-written ``pyproject.toml`` silently
  lost ``pyreadr``/``pandas``/``numpy``; every scraper that imported them would
  have died at import time on the next CI run.

Both are import-time failures, which is exactly what a daily cron discovers at
5am and a test discovers in one second.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PY_DIR = Path(__file__).resolve().parents[1] / "python"
SCRIPTS = sorted(p for p in PY_DIR.glob("*.py"))

# Renumbered 2026-08-02 to the ecosystem-wide ESPN-raw canon, so a stage number
# means the same dataset in every -raw repo: 01 schedules, 02 pbp, 03 standings,
# 04 game_rosters, 05 draft, 06 player_stats, 07 team_stats, 08 team_rosters,
# 09 player_core, 10+ league extras. Unlike the WBB twin, WNBA HAS a draft (05),
# and this repo has no 00_all sweep or 99 master stage.
EXPECTED = [
    "espn_wnba_01_schedules_scrape.py",
    "espn_wnba_02_pbp_scrape.py",
    "espn_wnba_03_standings_scrape.py",
    "espn_wnba_04_game_rosters_scrape.py",
    "espn_wnba_05_draft_scrape.py",
    "espn_wnba_06_player_stats_scrape.py",
    "espn_wnba_07_team_stats_scrape.py",
    "espn_wnba_08_team_rosters_scrape.py",
    "espn_wnba_09_player_core_scrape.py",
    "espn_wnba_10_officials_scrape.py",
]


def test_the_numbered_scripts_are_exactly_what_we_expect():
    """Numbers are run order. A gap or a stray file means the pipeline and the
    directory listing have diverged."""
    assert [p.name for p in SCRIPTS] == EXPECTED


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_script_imports(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(path.stem, None)


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_script_help_exits_zero(path):
    proc = subprocess.run(
        [sys.executable, str(path), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--start_year" in proc.stdout


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_no_script_uses_type_bool(path):
    """``argparse(type=bool)`` is the defect that made every daily run
    re-download the whole archive: bash passes "false" and bool("false") is
    True. Nothing may reintroduce it.

    Checked against the AST, not the text -- a comment explaining the
    antipattern is fine, an ``add_argument(type=bool)`` call is not.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "type" and isinstance(kw.value, ast.Name) and kw.value.id == "bool"
    ]
    assert offenders == [], (
        f"{path.name} passes type=bool at line(s) {offenders}; use sportsdataverse.scrape.espn.cli.str2bool"
    )
