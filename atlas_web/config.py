"""Paths and settings for atlas_web. Data lives in git-ignored atlas_web/data/ (override: ATLAS_WEB_DATA)."""

import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "atlas_web"
STATIC = PKG / "static"
SETTINGS_FILE = REPO / "config" / "atlas_web.json"
PLATFORM_LOG = REPO / "runs" / "platform_jobs.log"  # one daily cap shared by every workspace and the CLI


def data_dir() -> Path:
    return Path(os.environ.get("ATLAS_WEB_DATA") or PKG / "data")


def settings() -> dict:
    return json.loads(SETTINGS_FILE.read_text())


def limits() -> dict:
    return settings()["limits"]
