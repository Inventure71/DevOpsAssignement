#!/usr/bin/env python3
"""Install the pinned Drive pack once, or verify it offline with --check."""

import argparse
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.demo_pack import install, installed_path, load_source, validate_installed
from tools.launch_support import LaunchError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive", type=Path, help="Install from an already downloaded ZIP"
    )
    parser.add_argument(
        "--check", action="store_true", help="Offline, read-only integrity check"
    )
    options = parser.parse_args(argv)
    if options.check and options.archive:
        parser.error(
            "--check verifies the installed pack; use --archive only for installation"
        )
    try:
        if options.check:
            source = load_source(ROOT)
            if source is None:
                raise ValueError("The pinned Demo pack source is missing")
            target = validate_installed(installed_path(ROOT, source), source)
        else:
            target = install(ROOT, archive=options.archive)
        print(f"Demo music verified: 100 clips in {target}")
        print(
            "Run bash tools/run_demo.sh, or py -3 tools/launch_game.py demo on Windows."
        )
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, LaunchError) as error:
        parser.exit(1, f"Cannot prepare Demo music: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
