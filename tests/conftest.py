"""Shared test setup: lets tests import the pipeline (src/) and the app's helpers (app/)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for folder in ("src", "app"):
    sys.path.insert(0, str(REPO_ROOT / folder))
