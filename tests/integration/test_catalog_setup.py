import csv
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from backend.catalog.store import CatalogStore
from tools import catalog_download, setup_catalog


@pytest.fixture
def publisher():
    state = {"body": b"0123456789abcdef", "mode": "normal", "ranges": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(state["body"])))
            self.send_header("ETag", '"fixture-v1"')
            self.end_headers()

        def do_GET(self):
            if self.path.endswith(".sha256"):
                body = hashlib.sha256(state["body"]).hexdigest().encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            requested = self.headers.get("Range")
            state["ranges"].append(requested)
            offset = (
                int(requested.removeprefix("bytes=").removesuffix("-"))
                if requested
                else 0
            )
            if state["mode"] == "ignore_range":
                offset = 0
            body = state["body"][offset:]
            self.send_response(206 if offset else 200)
            if offset:
                start = offset + 1 if state["mode"] == "wrong_range" else offset
                self.send_header(
                    "Content-Range",
                    f"bytes {start}-{len(state['body']) - 1}/{len(state['body'])}",
                )
            length = len(body) + 1 if state["mode"] == "wrong_length" else len(body)
            self.send_header("Content-Length", str(length))
            self.end_headers()
            if state["mode"] == "interrupt":
                body = body[:8]
            elif state["mode"] == "bad_hash":
                body = b"X" * len(body)
            self.wfile.write(body)
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/fixture.tar.zst", state
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_download_and_reuse_require_matching_sha256(tmp_path, publisher):
    url, state = publisher
    info = catalog_download.archive_info(url)
    destination = tmp_path / "downloads/archive.tar.zst"
    assert (
        catalog_download.download_archive(info, destination).read_bytes()
        == state["body"]
    )
    assert (
        json.loads(
            destination.with_name(destination.name + ".verified.json").read_text()
        )
        == info
    )
    catalog_download.download_archive(info, destination)
    assert state["ranges"] == [None]
    destination.write_bytes(b"X" * len(state["body"]))
    with pytest.raises(ValueError, match="Existing archive failed"):
        catalog_download.download_archive(info, destination)


@pytest.mark.parametrize("resume_mode", ["normal", "ignore_range"])
def test_interrupted_download_resumes_or_restarts_if_range_ignored(
    tmp_path, publisher, monkeypatch, resume_mode
):
    url, state = publisher
    monkeypatch.setattr(catalog_download, "CHUNK_BYTES", 4)
    info = catalog_download.archive_info(url)
    destination = tmp_path / "archive.tar.zst"
    state["mode"] = "interrupt"
    with pytest.raises(ValueError, match="ended before"):
        catalog_download.download_archive(info, destination)
    assert not destination.exists()
    assert (
        destination.with_name(destination.name + ".part").read_bytes()
        == state["body"][:8]
    )
    assert not destination.with_name(destination.name + ".verified.json").exists()
    state["mode"] = resume_mode
    catalog_download.download_archive(info, destination)
    assert state["ranges"] == [None, "bytes=8-"]
    assert destination.read_bytes() == state["body"]


@pytest.mark.parametrize(
    "mode, message", [("wrong_length", "Content-Length"), ("bad_hash", "SHA-256")]
)
def test_invalid_download_is_never_published(tmp_path, publisher, mode, message):
    url, state = publisher
    info = catalog_download.archive_info(url)
    state["mode"] = mode
    destination = tmp_path / "archive.tar.zst"
    with pytest.raises(ValueError, match=message):
        catalog_download.download_archive(info, destination)
    assert not destination.exists()
    assert not destination.with_name(destination.name + ".verified.json").exists()
    state["mode"] = "normal"
    assert (
        catalog_download.download_archive(info, destination).read_bytes()
        == state["body"]
    )


def test_invalid_resume_range_does_not_append(tmp_path, publisher, monkeypatch):
    url, state = publisher
    monkeypatch.setattr(catalog_download, "CHUNK_BYTES", 4)
    info = catalog_download.archive_info(url)
    destination = tmp_path / "archive.tar.zst"
    state["mode"] = "interrupt"
    with pytest.raises(ValueError):
        catalog_download.download_archive(info, destination)
    state["mode"] = "wrong_range"
    with pytest.raises(ValueError, match="Content-Range"):
        catalog_download.download_archive(info, destination)
    assert destination.with_name(destination.name + ".part").stat().st_size == 8


@pytest.mark.parametrize(
    "url",
    [
        "http://data.metabrainz.org/pub/musicbrainz/canonical_data/x.tar.zst",
        "https://example.org/data.tar.zst",
        "https://data.metabrainz.org.evil.invalid/data.tar.zst",
        "https://data.metabrainz.org/pub/musicbrainz/canonical_data/../../secret",
        "https://data.metabrainz.org/pub/musicbrainz/canonical_data/musicbrainz-canonical-dump-20261003-080003/musicbrainz-canonical-dump-20261003-080003.tar.zst.sha256",
    ],
)
def test_cli_rejects_non_official_sources(url):
    with pytest.raises(ValueError, match="official HTTPS"):
        setup_catalog.official_url(url)


def test_info_has_no_filesystem_or_zstd_dependency(tmp_path, monkeypatch, capsys):
    info = {
        "url": "fixture",
        "bytes": 2379610408,
        "sha256": "a" * 64,
        "validator": "fixture",
    }
    monkeypatch.setattr(setup_catalog, "archive_info", lambda *args, **kwargs: info)
    monkeypatch.setattr(setup_catalog.shutil, "which", lambda command: None)
    data = tmp_path / "not-created"
    assert setup_catalog.main(["--info", "--data-dir", str(data)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["import_rows"] == 100000
    assert report["bytes"] == 2379610408
    assert "full compressed archive" in report["note"]
    assert not data.exists()


def test_missing_zstd_fails_before_network_or_files(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_catalog.shutil, "which", lambda command: None)
    monkeypatch.setattr(
        setup_catalog, "archive_info", lambda *a, **k: pytest.fail("Network called")
    )
    data = tmp_path / "not-created"
    assert setup_catalog.main(["--data-dir", str(data)]) == 1
    assert not data.exists()


@pytest.fixture
def compressed_catalog(tmp_path):
    zstd = shutil.which("zstd")
    if zstd is None:
        pytest.skip("zstd is unavailable on PATH")
    text = io.StringIO(newline="")
    writer = csv.writer(text)
    writer.writerow(
        [
            "recording_mbid",
            "recording_name",
            "artist_credit_name",
            "artist_mbids",
            "score",
        ]
    )
    for number in range(3):
        writer.writerow(
            [
                f"00000000-0000-4000-8000-{number:012d}",
                f"Song {number}",
                "Artist",
                "{00000000-0000-4000-8000-000000000123}",
                str(number),
            ]
        )
    source = io.BytesIO()
    with tarfile.open(fileobj=source, mode="w") as bundle:
        for name, body in [
            ("dump/COPYING", b"CC0"),
            ("dump/canonical/canonical_musicbrainz_data.csv", text.getvalue().encode()),
            ("../../unwanted-file", b"never extract this"),
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(body)
            bundle.addfile(member, io.BytesIO(body))
    archive = tmp_path / "fixture.tar.zst"
    archive.write_bytes(
        subprocess.run(
            [zstd, "-q", "-c"], input=source.getvalue(), check=True, capture_output=True
        ).stdout
    )
    return archive, zstd


@pytest.mark.parametrize("limit, expected", [(1, 1), (None, 3)])
def test_streaming_import_uses_only_csv_without_extracting_archive(
    tmp_path, compressed_catalog, limit, expected
):
    archive, zstd = compressed_catalog
    database = tmp_path / "runtime/catalog.sqlite3"
    result = setup_catalog.import_archive(archive, database, zstd, limit)
    assert result == {"rows_read": expected, "imported": expected, "skipped": 0}
    store = CatalogStore(database)
    with store.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM catalog_songs").fetchone()[0]
            == expected
        )
    assert not (tmp_path / "unwanted-file").exists()
    assert not list(tmp_path.rglob("*.csv"))
    # Import is idempotent even if interrupted previously after a committed batch.
    setup_catalog.import_archive(archive, database, zstd, limit)
    with store.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM catalog_songs").fetchone()[0]
            == expected
        )


def test_full_import_detects_corrupt_decompressor_tail(tmp_path, compressed_catalog):
    archive, zstd = compressed_catalog
    archive.write_bytes(archive.read_bytes()[:-4])
    with pytest.raises((ValueError, tarfile.TarError)):
        setup_catalog.import_archive(archive, tmp_path / "catalog.sqlite3", zstd, None)


@pytest.mark.parametrize("unsafe", [False, True])
def test_import_rejects_duplicate_or_unsafe_csv_member(
    tmp_path, compressed_catalog, unsafe
):
    archive, zstd = compressed_catalog
    decoded = subprocess.run(
        [zstd, "-dc", str(archive)], check=True, capture_output=True
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(decoded)) as bundle:
        csv_bytes = bundle.extractfile(
            "dump/canonical/canonical_musicbrainz_data.csv"
        ).read()
    rewritten = io.BytesIO()
    names = (
        ["../canonical_musicbrainz_data.csv"]
        if unsafe
        else [
            "dump/canonical/canonical_musicbrainz_data.csv",
            "second/canonical_musicbrainz_data.csv",
        ]
    )
    with tarfile.open(fileobj=rewritten, mode="w") as bundle:
        for name in names:
            member = tarfile.TarInfo(name)
            member.size = len(csv_bytes)
            bundle.addfile(member, io.BytesIO(csv_bytes))
    archive.write_bytes(
        subprocess.run(
            [zstd, "-q", "-c"],
            input=rewritten.getvalue(),
            check=True,
            capture_output=True,
        ).stdout
    )
    with pytest.raises(ValueError, match="Duplicate or unsafe"):
        setup_catalog.import_archive(archive, tmp_path / "catalog.sqlite3", zstd, None)


def test_import_into_application_database_preserves_private_domain_tables(
    tmp_path, compressed_catalog
):
    from backend.storage.database import Database

    archive, zstd = compressed_catalog
    database = tmp_path / "whos_on_repeat.sqlite3"
    db = Database(database)
    db.initialize()
    with db.transaction() as connection:
        connection.execute(
            "INSERT INTO rooms (id,code,mode,created_at_ms) VALUES ('room','ABC123','demo',1000)"
        )
    assert setup_catalog.import_archive(archive, database, zstd, None)["imported"] == 3
    with db.read() as connection:
        assert connection.execute("SELECT code FROM rooms").fetchone()[0] == "ABC123"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert (
            connection.execute("SELECT COUNT(*) FROM catalog_songs").fetchone()[0] == 3
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.mark.parametrize("corrupt", [False, True])
def test_cli_download_import_and_provenance_are_real_pipeline(
    tmp_path, publisher, compressed_catalog, monkeypatch, corrupt
):
    url, state = publisher
    archive, zstd = compressed_catalog
    state["body"] = archive.read_bytes()[:-4] if corrupt else archive.read_bytes()
    # Production URL validation remains strict; only this local-server test
    # substitutes the transport, keeping actual checksum/download/tar/SQLite.
    monkeypatch.setattr(setup_catalog, "official_url", lambda value, **kwargs: value)
    monkeypatch.setattr(setup_catalog, "official_open", catalog_download._open)
    data = tmp_path / "configured-data"
    monkeypatch.setenv("DATA_DIR", str(data))
    code = setup_catalog.main(["--url", url, "--all"])
    downloaded = data / "catalog-downloads/fixture.tar.zst"
    assert downloaded.exists()
    assert downloaded.with_name(downloaded.name + ".verified.json").exists()
    provenance = downloaded.with_name(downloaded.name + ".imported.json")
    if corrupt:
        assert code == 1
        assert not provenance.exists()
    else:
        assert code == 0
        result = json.loads(provenance.read_text())
        assert result["imported"] == 3
        assert result["limit"] is None
        assert result["sha256"] == hashlib.sha256(state["body"]).hexdigest()
        assert setup_catalog.main(["--url", url, "--all"]) == 0
        assert state["ranges"] == [None]  # Verified archive reused on rerun.
    assert not list(data.rglob("*.csv"))
