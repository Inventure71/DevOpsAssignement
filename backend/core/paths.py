"""Resolve checkout resources and the pinned Demo installation independently of cwd."""

import json
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
CATALOG_PATH = PROJECT_ROOT / "catalog/demo_catalog.json"
MIGRATIONS_DIR = PROJECT_ROOT / "backend/storage/migrations"


def pinned_demo_pack_path(root=PROJECT_ROOT, source=None):
    """Locate the immutable installation selected by the committed source pin."""
    root = Path(root)
    if source is None:
        source = json.loads(
            (root / "catalog/demo_pack_source.json").read_text(encoding="utf-8")
        )
    if not isinstance(source, dict) or not (
        isinstance(source.get("pack"), str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source["pack"])
        and isinstance(source.get("sha256"), str)
        and re.fullmatch(r"[a-f0-9]{64}", source["sha256"])
    ):
        raise ValueError("Invalid pinned Demo pack location")
    return root / "catalog/local/packs" / (source["pack"] + "-" + source["sha256"][:12])
