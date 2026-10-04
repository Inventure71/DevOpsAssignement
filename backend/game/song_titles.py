"""Guess equivalence for release editions, separate from recording identity."""

import re
import unicodedata

from backend.catalog.identity import recording_title

_RELEASE = (
    r"(?:taylor['’]s\s+version|(?:\d{4}\s+)?remaster(?:ed)?(?:\s+\d{4})?"
    r"|deluxe\s+edition)"
)
_CREDIT = r"(?:feat\.?|ft\.?|featuring)\s+[^\])]+"
_LABEL = rf"(?:{_RELEASE}|{_CREDIT})"
_SUFFIX = re.compile(
    rf"\s*(?:\({_LABEL}\)|\[{_LABEL}\]|\s+[-–—]\s+{_RELEASE})\s*$",
    re.IGNORECASE,
)


def guess_title(value):
    """Remove recognized trailing release/credit labels, preserving musical versions."""
    text = unicodedata.normalize("NFKC", str(value))
    while (suffix := _SUFFIX.search(text)) is not None:
        text = text[: suffix.start()]
    return recording_title(text)
