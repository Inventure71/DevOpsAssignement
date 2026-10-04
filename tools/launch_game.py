#!/usr/bin/env python3
"""Prepare dependencies and music, then start Demo or Real."""

import argparse
import os
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if sys.version_info < (3, 12):
    raise SystemExit(
        "Python 3.12 or newer is required. Install it and rerun this launcher."
    )

from tools.launch_environment import build_environment
from tools.demo_pack import install, installed_path, load_source
from tools.launch_runtime import check_real_signing_key, prepare_python
from tools.launch_support import LaunchError, available_port, print_addresses


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("demo", "real"))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only configuration/dependency preflight; no install or server",
    )
    parser.add_argument(
        "--port", type=int, help="Local listening port (Demo default: 8000)"
    )
    parser.add_argument(
        "--data-dir", help="SQLite data directory, relative to the project or absolute"
    )
    parser.add_argument(
        "--playtest",
        action="store_true",
        help="Explicitly allow two-player testing and repeated Spotify accounts",
    )
    parser.add_argument(
        "--demo-pack", help="Directory of an already installed 100-song Demo pack"
    )
    options = parser.parse_args(argv)
    try:
        environment, warnings, description = build_environment(
            ROOT, options.mode, options, validate_pack=False
        )
        available_port(int(environment["PORT"]))
        python = prepare_python(ROOT, check=options.check)
        if options.mode == "real":
            check_real_signing_key(python, environment)
        if not options.check:
            source = load_source(ROOT)
            if source and environment["DEMO_PACK_DIR"] == str(
                installed_path(ROOT, source)
            ):
                if not installed_path(ROOT, source).is_dir():
                    print(
                        "Preparing Demo music from Drive once (about 98 MiB).",
                        flush=True,
                    )
                try:
                    install(ROOT)
                except (LaunchError, OSError, ValueError, zipfile.BadZipFile) as error:
                    raise LaunchError(
                        f"Demo music setup failed: {error}. "
                        "Retry tools/setup_demo_pack.py with internet access, or use "
                        "tools/setup_demo_pack.py --archive /path/to/the-pack.zip, "
                        "then rerun the launcher."
                    ) from error
        environment, warnings, description = build_environment(
            ROOT, options.mode, options
        )
        for warning in warnings:
            print("Note: " + warning, file=sys.stderr)
        print_addresses(options.mode, environment, description)
        if options.check:
            print("Preflight passed; no server started or application data changed.")
            return 0
        print("Starting server. Stop with Ctrl-C.", flush=True)
        os.chdir(ROOT)
        # Replace the launcher so Ctrl-C reaches the server.
        os.execve(str(python), [str(python), "-m", "backend"], environment)
    except (LaunchError, OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, "Cannot launch: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
