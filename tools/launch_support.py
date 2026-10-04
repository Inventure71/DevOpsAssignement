"""Launch errors, port availability, and human-readable playable addresses."""

import socket

from backend.api.invitations import discover_lan_host


class LaunchError(Exception):
    """An actionable preflight or setup failure, without exposing credentials."""


def available_port(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("0.0.0.0", port))
    except OSError:
        raise LaunchError(
            f"Port {port} is unavailable. Stop the server using it, or choose --port with another free port."
        ) from None


def print_addresses(mode, environment, description):
    port = int(environment["PORT"])
    if mode == "demo":
        print(f"Open on this computer: http://127.0.0.1:{port}/")
        host = discover_lan_host()
        if host:
            print(f"Open on other devices on the same network: http://{host}:{port}/")
        else:
            print(
                f"For other devices, use this computer's LAN IP and port {port}; automatic LAN detection was unavailable."
            )
        print(
            "Demo only: no API keys, account login, tunnel, or internet needed after dependency setup."
        )
    else:
        print("Open on every device: " + environment["APP_PUBLIC_URL"] + "/")
        print(
            f"Spotify and Demo available. Keep your HTTPS tunnel running and forwarding to local port {port}."
        )
        print(
            "Register and save this Spotify callback: "
            + environment["SPOTIFY_REDIRECT_URI"]
        )
    print("Music: " + description)
    if environment["PLAYTEST_MODE"].lower() in {"true", "1"}:
        print(
            "Playtest enabled: two players; repeated Spotify accounts allowed for testing."
        )
    else:
        print(
            "Standard rules: at least three players. Add --playtest for a two-player test."
        )
    print("Data directory: " + environment["DATA_DIR"])
