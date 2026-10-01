"""Resolve bundled resources from this checkout, independently of the shell cwd."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / 'frontend'
DEMO_ASSETS_DIR = PROJECT_ROOT / 'catalog/assets'
CATALOG_PATH = PROJECT_ROOT / 'catalog/demo_catalog.json'
MIGRATIONS_DIR = PROJECT_ROOT / 'backend/storage/migrations'
