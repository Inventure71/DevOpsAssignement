"""Literal environment settings and validated offline catalog selection."""

import os
from pathlib import Path
import re
import shlex
from urllib.parse import urlsplit

from backend.api.invitations import is_local_only
from tools.demo_pack import installed_path, load_source, validate_installed
from tools.demo_pack_validation import validate_demo_pack
from tools.launch_support import LaunchError


APPLICATION_KEYS = {
    "PORT",
    "DATA_DIR",
    "COOKIE_SECURE",
    "SETUP_TIMEOUT_MS",
    "GAME_MODE",
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_REDIRECT_URI",
    "APPLE_TEAM_ID",
    "APPLE_KEY_ID",
    "APPLE_PRIVATE_KEY_PATH",
    "APPLE_STOREFRONT",
    "APP_PUBLIC_URL",
    "PLAYTEST_MODE",
    "DEMO_PACK_DIR",
}


def read_dotenv(path):
    """Read literal KEY=value settings; never execute shell code or interpolate."""
    if not path.is_file():
        return {}
    result = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as error:
        raise LaunchError(f"Cannot read {path}: {error.strerror}") from None
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise LaunchError(f"Invalid .env setting on line {number}; use KEY=value.")
        try:
            tokens = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise LaunchError(f"Invalid quoting in .env on line {number}.") from None
        if len(tokens) > 1:
            raise LaunchError(
                f"Quote values containing spaces in .env on line {number}."
            )
        if key in APPLICATION_KEYS:
            result[key] = tokens[0] if tokens else ""
    return result


def project_path(value, root):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def configure_demo_pack(root, environment, requested=None, *, validate=True):
    """Resolve the sole Demo pack; preparation belongs to the launch entry point."""
    explicit = requested or environment.get("DEMO_PACK_DIR")
    if explicit:
        candidate = project_path(explicit, root)
        count = validate_demo_pack(candidate) if validate else None
    else:
        source = load_source(root)
        if source is None:
            raise LaunchError(
                "The pinned Demo source is missing; restore catalog/demo_pack_source.json."
            )
        candidate = installed_path(root, source)
        if validate:
            try:
                validate_installed(candidate, source)
            except (OSError, ValueError, LaunchError) as error:
                raise LaunchError(
                    f"The pinned Demo pack is missing or incomplete: {error}. "
                    "Run tools/setup_demo_pack.py, then rerun the launcher."
                ) from error
            count = source["song_count"]
        else:
            count = None
    environment["DEMO_PACK_DIR"] = str(candidate)
    return (
        [],
        f"local Demo pack ({count} clips)"
        if count
        else "local Demo pack (setup required)",
    )


def build_environment(root, mode, options, inherited=None, *, validate_pack=True):
    """The selected launch owns its mode, transport, and provider boundaries."""
    source = dict(os.environ if inherited is None else inherited)
    environment = {
        key: value for key, value in source.items() if key not in APPLICATION_KEYS
    }
    if mode == "real":
        settings = read_dotenv(root / ".env")
        settings.update(
            {key: value for key, value in source.items() if key in APPLICATION_KEYS}
        )
        environment.update(settings)
    environment["GAME_MODE"] = "demo" if mode == "demo" else "normal"
    environment["PORT"] = str(
        options.port if options.port is not None else environment.get("PORT", "8000")
    )
    try:
        port = int(environment["PORT"])
    except ValueError:
        raise LaunchError("PORT must be an integer between 1 and 65535.") from None
    if not 1 <= port <= 65535:
        raise LaunchError("PORT must be between 1 and 65535.")
    environment["DATA_DIR"] = str(
        project_path(
            options.data_dir
            or environment.get("DATA_DIR")
            or ("data/demo" if mode == "demo" else "data"),
            root,
        )
    )
    if options.playtest:
        environment["PLAYTEST_MODE"] = "true"
    else:
        environment.setdefault("PLAYTEST_MODE", "false")
    if environment["PLAYTEST_MODE"].lower() not in {"true", "false", "1", "0"}:
        raise LaunchError("PLAYTEST_MODE must be true or false.")
    try:
        timeout = int(environment.get("SETUP_TIMEOUT_MS", "60000"))
    except ValueError:
        raise LaunchError(
            "SETUP_TIMEOUT_MS must be between 10000 and 120000."
        ) from None
    if not 10_000 <= timeout <= 120_000:
        raise LaunchError("SETUP_TIMEOUT_MS must be between 10000 and 120000.")
    if mode == "demo":
        environment["COOKIE_SECURE"] = "false"
        environment["APP_PUBLIC_URL"] = ""
        # Demo setup is validated before the launch entry starts the server.
        warnings, pack_description = configure_demo_pack(
            root,
            environment,
            options.demo_pack,
            validate=validate_pack,
        )
        return environment, warnings, pack_description
    # Real games use one shared HTTPS origin, including the OAuth callback.
    public = environment.get("APP_PUBLIC_URL", "").rstrip("/")
    try:
        address = urlsplit(public)
        valid = (
            address.scheme == "https"
            and not is_local_only(address.hostname)
            and address.hostname
            and not address.username
            and not address.password
            and not address.path
            and not address.query
            and not address.fragment
        )
        _ = address.port
    except ValueError:
        valid = False
    if not valid:
        raise LaunchError(
            "Set APP_PUBLIC_URL in .env to the shared HTTPS origin for real games."
        )
    callback = public + "/api/music/spotify/callback"
    if environment.get("SPOTIFY_REDIRECT_URI", callback) != callback:
        raise LaunchError(
            "SPOTIFY_REDIRECT_URI must equal APP_PUBLIC_URL + /api/music/spotify/callback; save it in Spotify too."
        )
    environment["SPOTIFY_REDIRECT_URI"] = callback
    environment["APP_PUBLIC_URL"] = public
    environment["COOKIE_SECURE"] = "true"
    missing = [
        key
        for key in (
            "SPOTIFY_CLIENT_ID",
            "APPLE_TEAM_ID",
            "APPLE_KEY_ID",
            "APPLE_PRIVATE_KEY_PATH",
        )
        if not environment.get(key)
    ]
    if missing:
        raise LaunchError(
            "Configure these real-game settings in .env: " + ", ".join(missing)
        )
    key_path = project_path(environment["APPLE_PRIVATE_KEY_PATH"], root)
    if not key_path.is_file():
        raise LaunchError(
            "APPLE_PRIVATE_KEY_PATH must point to your readable Apple .p8 signing key."
        )
    try:
        key_path.read_bytes()
    except OSError:
        raise LaunchError("Cannot read APPLE_PRIVATE_KEY_PATH.") from None
    environment["APPLE_PRIVATE_KEY_PATH"] = str(key_path)
    environment.setdefault("APPLE_STOREFRONT", "es")
    if not re.fullmatch(r"[a-z]{2}", environment["APPLE_STOREFRONT"]):
        raise LaunchError(
            "APPLE_STOREFRONT must be a two-letter country code, for example es."
        )
    warnings, pack_description = configure_demo_pack(
        root,
        environment,
        options.demo_pack,
        validate=validate_pack,
    )
    description = (
        "Spotify listening history and Apple catalog; Demo: " + pack_description
    )
    return environment, warnings, description
