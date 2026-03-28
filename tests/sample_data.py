from __future__ import annotations

import shutil
from pathlib import Path

TEST_CAMPAIGN_SLUG = "linden-pass"
TEST_CAMPAIGN_TITLE = "Echoes of the Alloy Coast"

ASSIGNED_CHARACTER_SLUG = "arden-march"
ASSIGNED_CHARACTER_NAME = "Arden March"
SECOND_CHARACTER_SLUG = "selene-brook"
SECOND_CHARACTER_NAME = "Selene Brook"
THIRD_CHARACTER_SLUG = "tobin-slate"
THIRD_CHARACTER_NAME = "Tobin Slate"

TEST_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "sample_campaigns"


def build_test_campaigns_dir(tmp_path: Path) -> Path:
    campaigns_dir = tmp_path / "campaigns"
    shutil.copytree(TEST_FIXTURES_ROOT, campaigns_dir)
    return campaigns_dir
