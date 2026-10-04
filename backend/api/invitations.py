"""Build invitations using a reachable origin."""

import ipaddress
import socket
from urllib.parse import urlencode, urlsplit


def is_local_only(host: str | None) -> bool:
    if not host or host.lower() == "localhost" or host.lower().endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or address.is_unspecified
    except ValueError:
        return False


def discover_lan_host() -> str | None:
    """Read the outbound IPv4 address from the routing table."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 9))
            host = connection.getsockname()[0]
        address = ipaddress.ip_address(host)
        if address.is_private and not (
            address.is_loopback or address.is_link_local or address.is_unspecified
        ):
            return host
    except (OSError, ValueError):
        pass
    return None


class InviteLinks:
    def __init__(self, public_url: str = "", port: int = 8000):
        self.public_origin = None
        if public_url:
            parsed = urlsplit(public_url)
            if (
                parsed.scheme not in {"http", "https"}
                or is_local_only(parsed.hostname)
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "APP_PUBLIC_URL must be an HTTP(S) origin reachable by other devices"
                )
            # Validate a malformed port before starting the application.
            _ = parsed.port
            self.public_origin = f"{parsed.scheme}://{parsed.netloc}"
        host = discover_lan_host() if not self.public_origin else None
        self.lan_origin = f"http://{host}:{port}" if host else None

    def for_room(self, request_origin: str, code: str) -> str | None:
        parsed = urlsplit(request_origin)
        origin = self.public_origin
        if not origin:
            origin = (
                self.lan_origin
                if is_local_only(parsed.hostname)
                else f"{parsed.scheme}://{parsed.netloc}"
            )
        return f"{origin}/?{urlencode({'join': code})}" if origin else None
