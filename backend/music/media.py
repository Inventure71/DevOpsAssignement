"""Bounded preview delivery checks and conservative recording identity matching."""

from backend.catalog.identity import normalized_words, recording_title
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def allowed_preview_url(url):
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
            return False
    except ValueError:
        return False
    return host in {"audio-ssl.itunes.apple.com", "audio.itunes.apple.com"} or host.endswith(".mzstatic.com")


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_preview_url(newurl):
            raise ValueError("Preview provider redirected outside its permitted hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def probe_preview(url):
    if not allowed_preview_url(url):
        return False
    try:
        request = Request(url, headers={"Range": "bytes=0-255", "User-Agent": "WhosOnRepeat/1.0"})
        with build_opener(_SafeRedirect()).open(request, timeout=4) as response:
            content_type = response.headers.get_content_type()
            sample = response.read(256)
        recognized = sample.startswith(b"ID3") or (len(sample) >= 2 and sample[0] == 255 and sample[1] & 224 == 224)
        recognized = recognized or (len(sample) >= 12 and sample[4:8] == b"ftyp")
        return len(sample) >= 12 and (content_type.startswith("audio/") or recognized)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return False


def matches_recording(song, row):
    if not isinstance(row.get("title"), str) or not isinstance(row.get("artist"), str):
        return False
    if recording_title(song["title"]) != recording_title(row.get("title", "")):
        return False
    credits = song.get("artists") or []
    lead_artist = credits[0]["name"] if credits else song.get("artist", "")
    provider_artist = row.get("artist", "")
    if normalized_words(lead_artist) == normalized_words(provider_artist):
        return True
    provider_credits = row.get("artists") or []
    return any(isinstance(credit, dict) and normalized_words(credit.get("name", "")) == normalized_words(lead_artist)
               for credit in provider_credits)
