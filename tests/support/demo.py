"""Isolated transport media for tests; runtime always uses the installed pack."""

import json
import wave
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.core.config import Config
from backend.core.paths import CATALOG_PATH


def make_demo_pack(path, *, entries=None):
    """Supply valid 30-second WAVs for canonical or explicit test metadata."""
    path = Path(path)
    clips = path / "assets/clips"
    clips.mkdir(parents=True, exist_ok=True)
    if entries is None:
        entries = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        if len(entries) != 100:
            raise ValueError(
                "Transport fixtures require the canonical 100-song catalog"
            )
    else:
        entries = json.loads(json.dumps(entries))
    audio = BytesIO()
    with wave.open(audio, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(1)
        recording.setframerate(8000)
        recording.writeframes(bytes([128]) * 8000 * 30)
    content = audio.getvalue()
    for entry in entries:
        filename = entry["id"] + ".wav"
        if Path(filename).name != filename or "\\" in filename:
            raise ValueError("Unsafe transport fixture song ID")
        (clips / filename).write_bytes(content)
        entry["preview_url"] = "/static/demo/local/clips/" + filename
        entry["artwork_url"] = None
    (path / "demo_catalog.json").write_text(
        json.dumps(entries, ensure_ascii=False), encoding="utf-8"
    )
    (path / "assets/credits.html").write_text(
        "<!doctype html><title>Test media</title>Silent transport fixtures.",
        encoding="utf-8",
    )
    return path


@lru_cache(maxsize=1)
def _shared_pack():
    directory = TemporaryDirectory(prefix="repeat-test-media-")
    return directory, make_demo_pack(Path(directory.name))


def shared_demo_pack():
    """Reuse immutable test media for this test process without app data reuse."""
    return _shared_pack()[1]


def demo_config(*args, **kwargs):
    """Build real application configuration with explicit isolated test media."""
    if "demo_pack_dir" not in kwargs:
        kwargs["demo_pack_dir"] = shared_demo_pack()
    return Config(*args, **kwargs)


def prepared_demo_import(conn, *, include_decoys=True):
    """Supply prepared source facts to tests focused on Rooms persistence."""
    from backend.music.sources import DemoListeningAdapter
    from backend.rooms.demo import catalog_snapshot

    pools = catalog_snapshot(conn)
    listening = DemoListeningAdapter(pools["personal"]).read()
    return {
        "provider": listening.provider,
        "evidence": listening.evidence,
        "account_id": listening.account_id,
        "songs": listening.songs,
        "observed_songs": listening.songs,
        "decoys": pools["decoy"][:20] if include_decoys else [],
    }
