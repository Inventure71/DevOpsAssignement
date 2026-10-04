"""Pure normalization of recording titles and individually credited artist names."""

import re
import unicodedata


def normalized_words(value):
    text = unicodedata.normalize("NFKD", str(value)).casefold()
    text = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"\w+", text))


def recording_title(value):
    # Credits can move between provider title and artist fields. Version labels
    # (live, remix, instrumental, remaster) still distinguish the recording.
    text = re.sub(
        r"\s*[\[(](?:feat\.?|ft\.?|featuring)\s+[^\])]+[\])]\s*$",
        "",
        str(value),
        flags=re.I,
    )
    return normalized_words(text)
