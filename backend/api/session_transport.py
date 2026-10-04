"""Keep browser admission on a transport that can retain its session cookies."""

from urllib.parse import urlsplit

from backend.core.errors import DomainError


def https_game_url(config):
    # APP_PUBLIC_URL is validated as an origin by the invitation boundary.
    if urlsplit(config.public_url).scheme == "https":
        return config.public_url.rstrip("/") + "/"
    return None


def check_session_transport(request, config):
    if not config.cookie_secure or request.url.scheme == "https":
        return
    path = request.url.path
    room_api = path == "/api/rooms" or path.startswith("/api/rooms/")
    music_session_api = (
        path.startswith("/api/music/spotify/") and path != "/api/music/spotify/config"
    )
    if not (room_api or music_session_api):
        return
    address = https_game_url(config)
    raise DomainError(
        "session_https_required",
        "Open the shared HTTPS game address to create or join a room."
        if address
        else "The host must configure an HTTPS game address before creating or joining rooms.",
        409,
        {"application_url": address} if address else {},
    )
