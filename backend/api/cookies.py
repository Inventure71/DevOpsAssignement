"""Issue room-scoped browser credentials and enforce their retention lifetime."""

from backend.rooms.service import RETENTION_MS


def cookie_name(room_id):
    return "repeat_" + room_id


def issue_cookie(response, config, admission, now):
    room = admission["room"]
    expiry = (room["last_completed_at_ms"] or room["created_at_ms"]) + RETENTION_MS
    response.set_cookie(
        cookie_name(room["id"]),
        admission["token"],
        max_age=max(0, (expiry - now) // 1000),
        path="/api/rooms/" + room["id"],
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
    )
