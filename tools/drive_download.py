"""Anonymous, bounded Google Drive ZIP downloads with pinned integrity checks."""

from contextlib import closing
import hashlib
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from http.client import HTTPException
from pathlib import Path
import tempfile
from time import monotonic
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPCookieProcessor,
    Request,
    build_opener,
)

ALLOWED_HOSTS = {"drive.google.com", "drive.usercontent.google.com"}
CHUNK_BYTES = 1024 * 1024


def safe_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Drive download redirected outside the allowed HTTPS hosts")
    return url


class DriveRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, url):
        safe_url(url)
        return super().redirect_request(request, response, code, message, headers, url)


class ConfirmationForm(HTMLParser):
    """Parse a bounded Google download-confirmation form."""

    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
        self.inside = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "download-form":
            self.inside = True
            self.action = attrs.get("action")
        elif tag == "input" and self.inside and attrs.get("type") == "hidden":
            self.fields[attrs.get("name")] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.inside = False

    def url(self, file_id):
        if (
            not self.action
            or self.fields.get("id") != file_id
            or self.fields.get("export") != "download"
            or not self.fields.get("confirm")
            or set(self.fields) - {"id", "export", "confirm", "uuid", "resourcekey"}
        ):
            raise ValueError(
                "Drive did not offer the ZIP download; check sharing or download quota"
            )
        return safe_url(self.action) + "?" + urlencode(self.fields)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_archive(path, source):
    if path.stat().st_size != source["bytes"] or sha256(path) != source["sha256"]:
        raise ValueError("Demo ZIP size or SHA-256 disagrees with the pinned pack")


def download(source, destination, *, opener=None, progress=print):
    """Publish only complete verified bytes; interrupted downloads leave no ZIP."""
    try:
        return _download(source, destination, opener=opener, progress=progress)
    except HTTPException as error:
        raise ValueError(f"Drive transfer failed: {error}") from None


def _download(source, destination, *, opener, progress):
    destination = Path(destination)
    if destination.is_file():
        verify_archive(destination, source)
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    opener = opener or build_opener(DriveRedirects(), HTTPCookieProcessor(CookieJar()))
    url = "https://drive.google.com/uc?" + urlencode(
        {"export": "download", "id": source["file_id"]}
    )
    deadline = monotonic() + 300
    for attempt in range(2):
        request = Request(safe_url(url), headers={"Accept-Encoding": "identity"})
        with closing(opener.open(request, timeout=20)) as response:
            safe_url(response.geturl())
            if response.status != 200 or response.headers.get("Content-Range"):
                raise ValueError("Drive returned a partial or unsuccessful download")
            if "text/html" in response.headers.get("Content-Type", ""):
                page = response.read(65537)
                if attempt or len(page) > 65536:
                    raise ValueError(
                        "Drive refused the download; check sharing or quota"
                    )
                form = ConfirmationForm()
                form.feed(page.decode("utf-8"))
                url = form.url(source["file_id"])
                continue
            length = response.headers.get("Content-Length")
            if length and int(length) != source["bytes"]:
                raise ValueError("Drive ZIP size disagrees with the pinned pack")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=destination.parent, prefix=".download-", delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    received = 0
                    last_report = 0
                    while chunk := response.read(CHUNK_BYTES):
                        received += len(chunk)
                        if received > source["bytes"] or monotonic() > deadline:
                            raise ValueError(
                                "Drive download exceeded its size or time limit"
                            )
                        stream.write(chunk)
                        if progress and received - last_report >= 10 * CHUNK_BYTES:
                            progress(
                                f"Downloading Demo music: {received / source['bytes']:.0%}"
                            )
                            last_report = received
                verify_archive(temporary, source)
                temporary.replace(destination)
                return destination
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
    raise ValueError("Drive did not return the music ZIP")
