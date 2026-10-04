"""Pinned download and publication boundaries used by real launcher setup."""

import hashlib
from http.client import BadStatusLine, IncompleteRead
from io import BytesIO
import json
from pathlib import Path
import stat
import zipfile

import pytest

from tools import demo_pack, drive_download, launch_environment, launch_game
from tools.launch_support import LaunchError


def digest(value):
    return hashlib.sha256(value).hexdigest()


def build_zip(root, transform=None, *, invalid_catalog=False):
    """Small transport assets, with the actual 100-song schema and signed inventory."""
    files = {"provenance.json": b"{}", "assets/credits.html": b"Fixture music credits"}
    catalog = []
    for index in range(100):
        name = f"assets/clips/fixture-{index}.m4a"
        files[name] = b"fixture-original-bytes-" + str(index).encode()
        catalog.append(
            dict(
                id=f"fixture-{index}",
                pool_kind="personal" if index < 80 else "decoy",
                title=f"Song {index}",
                artist="Fixture Artist",
                isrc=None,
                artists=[dict(artist_key="demo:fixture", name="Fixture Artist")],
                preview_url=f"/static/demo/local/clips/fixture-{index}.m4a",
                artwork_url=None,
            )
        )
    if invalid_catalog:
        catalog[0]["artists"] = []
    files["demo_catalog.json"] = json.dumps(catalog).encode()
    manifest = dict(
        schema_version=1,
        pack="whos-on-repeat-demo-100",
        song_count=100,
        pools={"personal": 80, "decoy": 20},
        files={
            name: dict(bytes=len(value), sha256=digest(value))
            for name, value in files.items()
        },
    )
    files["pack-manifest.json"] = json.dumps(manifest).encode()
    entries = list(files.items())
    if transform:
        entries = transform(entries)
    archive = root / "pack.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, value in entries:
            zipped.writestr(name, value)
    source = dict(
        schema_version=1,
        pack=manifest["pack"],
        file_id="fixtureDriveId123",
        bytes=archive.stat().st_size,
        sha256=drive_download.sha256(archive),
        manifest_sha256=digest(files["pack-manifest.json"]),
        song_count=100,
        pools=manifest["pools"],
    )
    (root / "catalog").mkdir(exist_ok=True)
    (root / "catalog/demo_pack_source.json").write_text(json.dumps(source))
    return archive, source


class Response(BytesIO):
    def __init__(self, value, *, headers=None, status=200, url=None):
        super().__init__(value)
        self.headers = headers or {}
        self.status = status
        self.url = url or "https://drive.usercontent.google.com/download"

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def open(self, request, **kwargs):
        self.calls.append(request.full_url)
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


def source_for(value):
    return dict(file_id="fixtureDriveId123", bytes=len(value), sha256=digest(value))


def test_google_confirmation_form_followed_by_checksum_verified_download(tmp_path):
    page = b"""<form id="download-form" action="https://drive.usercontent.google.com/download">
        <input type="hidden" name="id" value="fixtureDriveId123">
        <input type="hidden" name="export" value="download">
        <input type="hidden" name="confirm" value="t">
        <input type="hidden" name="uuid" value="a&amp;b"></form>"""
    value = b"verified fixture ZIP"
    opener = Opener(
        [Response(page, headers={"Content-Type": "text/html"}), Response(value)]
    )
    target = tmp_path / "download.zip"
    assert drive_download.download(source_for(value), target, opener=opener) == target
    assert target.read_bytes() == value and "uuid=a%26b" in opener.calls[1]
    offline = Opener([])
    drive_download.download(source_for(value), target, opener=offline)
    assert offline.calls == []


@pytest.mark.parametrize(
    "fault",
    [
        "truncated",
        "oversized",
        "wrong-hash",
        "partial",
        "length",
        "private",
        "html-limit",
        "outside-host",
        "timeout",
        "bad-status",
        "incomplete-read",
    ],
)
def test_failed_download_publishes_no_zip_or_temporary_bytes(tmp_path, fault):
    value = b"expected verified download"
    response = Response(value)
    if fault == "truncated":
        response = Response(value[:-1])
    elif fault == "oversized":
        response = Response(value + b"extra")
    elif fault == "wrong-hash":
        response = Response(b"x" * len(value))
    elif fault == "partial":
        response.status = 206
    elif fault == "length":
        response.headers["Content-Length"] = "1"
    elif fault in {"private", "html-limit"}:
        response = Response(
            b"x" * (65537 if fault == "html-limit" else 10),
            headers={"Content-Type": "text/html"},
        )
    elif fault == "outside-host":
        response.url = "https://example.com/download"
    elif fault == "bad-status":
        response = BadStatusLine("broken proxy response")
    elif fault == "incomplete-read":
        response = IncompleteRead(b"truncated", len(value))
    else:
        response = TimeoutError("unavailable")
    target = tmp_path / "download.zip"
    with pytest.raises((ValueError, OSError)):
        drive_download.download(source_for(value), target, opener=Opener([response]))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "url",
    [
        "http://drive.google.com/file",
        "https://example.com/file",
        "https://user@drive.google.com/file",
        "https://drive.google.com:444/file",
    ],
)
def test_redirects_are_rejected_before_following_untrusted_targets(url):
    with pytest.raises(ValueError):
        drive_download.DriveRedirects().redirect_request(None, None, 302, "", {}, url)


def test_install_publication_is_atomic_and_rerun_is_entirely_offline(
    tmp_path, monkeypatch
):
    archive, source = build_zip(tmp_path)
    local = tmp_path / "catalog/local"
    local.mkdir()
    (local / "user-note.txt").write_bytes(b"unrelated local file")
    pack = demo_pack.install(tmp_path, archive=archive)
    assert pack == demo_pack.installed_path(tmp_path, source)
    assert demo_pack.validate_installed(pack, source) == pack
    assert (local / "user-note.txt").read_bytes() == b"unrelated local file"
    assert not (local / ".drive-install.lock").exists()
    monkeypatch.setattr(
        demo_pack, "download", lambda *a, **kw: pytest.fail("No network on rerun")
    )
    assert demo_pack.install(tmp_path) == pack
    environment = {}
    notes, description = launch_environment.configure_demo_pack(tmp_path, environment)
    assert not notes and description == "local Demo pack (100 clips)"
    assert environment["DEMO_PACK_DIR"] == str(pack)


def test_unmanaged_pack_is_not_selected_instead_of_pinned_installation(tmp_path):
    from tests.unit.test_launchers import make_pack

    archive, source = build_zip(tmp_path)
    make_pack(tmp_path / "catalog/local")
    installed = demo_pack.install(tmp_path, archive=archive)
    environment = {}
    launch_environment.configure_demo_pack(tmp_path, environment)
    assert environment["DEMO_PACK_DIR"] == str(installed)
    assert installed == demo_pack.installed_path(tmp_path, source)


@pytest.mark.parametrize(
    "fault",
    [
        "checksum",
        "manifest",
        "missing-asset",
        "catalog",
        "unsafe",
        "duplicate",
        "symlink",
        "expanded",
    ],
)
def test_failed_install_never_selects_a_partial_pack_or_changes_unrelated_files(
    tmp_path, fault, monkeypatch
):
    transform = None
    if fault == "unsafe":
        transform = lambda entries: [
            ("../escaped" if i == 0 else n, v) for i, (n, v) in enumerate(entries)
        ]
    elif fault == "duplicate":
        transform = lambda entries: entries + [entries[0]]
    elif fault == "missing-asset":
        transform = lambda entries: [
            (name, b"changed media" if name == "assets/clips/fixture-0.m4a" else value)
            for name, value in entries
        ]
    elif fault == "symlink":

        def transform(entries):
            name, value = entries[0]
            linked = zipfile.ZipInfo(name)
            linked.external_attr = (stat.S_IFLNK | 0o777) << 16
            return [(linked, value)] + entries[1:]

    if fault == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive, source = build_zip(tmp_path, transform)
    else:
        archive, source = build_zip(
            tmp_path, transform, invalid_catalog=fault == "catalog"
        )
    if fault == "checksum":
        archive.write_bytes(archive.read_bytes()[:-1])
    elif fault == "manifest":
        source["manifest_sha256"] = "0" * 64
        (tmp_path / "catalog/demo_pack_source.json").write_text(json.dumps(source))
    elif fault == "expanded":
        monkeypatch.setattr(demo_pack, "MAX_EXPANDED_BYTES", source["bytes"] + 1)
    local = tmp_path / "catalog/local"
    local.mkdir()
    (local / "user-note.txt").write_bytes(b"unrelated local file")
    with pytest.raises((ValueError, OSError, zipfile.BadZipFile, LaunchError)):
        demo_pack.install(tmp_path, archive=archive)
    assert not demo_pack.installed_path(tmp_path, source).exists()
    assert (local / "user-note.txt").read_bytes() == b"unrelated local file"
    assert not (local / ".drive-install.lock").exists()
    assert not list((local / "packs").glob(".install-*"))
    assert not (tmp_path / "escaped").exists()


def test_corrupt_installed_asset_fails_offline_instead_of_downloading(
    tmp_path, monkeypatch
):
    archive, source = build_zip(tmp_path)
    pack = demo_pack.install(tmp_path, archive=archive)
    (pack / "assets/clips/fixture-0.m4a").write_bytes(b"changed")
    monkeypatch.setattr(
        demo_pack,
        "download",
        lambda *a, **kw: pytest.fail("Corruption is not a network cache miss"),
    )
    with pytest.raises(ValueError, match="verification"):
        demo_pack.install(tmp_path)


def test_concurrent_installer_does_not_remove_another_installers_lock(tmp_path):
    archive, _ = build_zip(tmp_path)
    lock = tmp_path / "catalog/local/.drive-install.lock"
    lock.parent.mkdir()
    lock.write_text("another process")
    with pytest.raises(ValueError, match="Another Demo installation"):
        demo_pack.install(tmp_path, archive=archive)
    assert lock.read_text() == "another process"


@pytest.mark.parametrize("flag", ["--check", "--demo-pack"])
def test_launcher_read_only_and_explicit_pack_never_download(
    tmp_path, monkeypatch, flag
):
    from tests.unit.test_launchers import make_pack

    archive, _ = build_zip(tmp_path)
    pack = demo_pack.install(tmp_path, archive=archive)
    monkeypatch.setattr(launch_game, "ROOT", tmp_path)
    monkeypatch.setattr(launch_game, "available_port", lambda *a: None)
    monkeypatch.setattr(launch_game, "prepare_python", lambda *a, **kw: Path("python"))
    monkeypatch.setattr(
        launch_game, "install", lambda *a, **kw: pytest.fail("No install")
    )
    monkeypatch.setattr(
        demo_pack, "download", lambda *a, **kw: pytest.fail("No download")
    )
    monkeypatch.setattr(launch_game.os, "chdir", lambda *a: None)
    calls = []
    monkeypatch.setattr(launch_game.os, "execve", lambda *a: calls.append(a))
    args = ["demo", flag]
    if flag == "--demo-pack":
        make_pack(tmp_path / "chosen")
        args.append(str(tmp_path / "chosen"))
    assert launch_game.main(args) == (0 if flag == "--check" else None)
    if flag == "--check":
        assert calls == []
        assert (
            demo_pack.validate_installed(pack, demo_pack.load_source(tmp_path)) == pack
        )
    else:
        assert calls[0][2]["DEMO_PACK_DIR"] == str(tmp_path / "chosen")


def test_missing_read_only_pack_cannot_download_or_start_server(
    tmp_path, monkeypatch, capsys
):
    _, source = build_zip(tmp_path)
    monkeypatch.setattr(launch_game, "ROOT", tmp_path)
    monkeypatch.setattr(launch_game, "available_port", lambda *a: None)
    monkeypatch.setattr(launch_game, "prepare_python", lambda *a, **kw: Path("python"))
    monkeypatch.setattr(
        launch_game,
        "install",
        lambda *a, **kw: pytest.fail("Read-only check cannot install"),
    )
    monkeypatch.setattr(
        demo_pack,
        "download",
        lambda *a, **kw: pytest.fail("Read-only check cannot download"),
    )
    monkeypatch.setattr(
        launch_game.os, "execve", lambda *a: pytest.fail("No server without music")
    )
    with pytest.raises(SystemExit) as failure:
        launch_game.main(["demo", "--check"])
    assert failure.value.code == 1
    message = capsys.readouterr().err
    assert "Cannot launch:" in message and "tools/setup_demo_pack.py" in message
    assert not demo_pack.installed_path(tmp_path, source).exists()
    assert not (tmp_path / "catalog/local").exists()


def test_first_launch_installs_then_passes_verified_pack_to_server(
    tmp_path, monkeypatch
):
    archive, source = build_zip(tmp_path)
    monkeypatch.setattr(launch_game, "ROOT", tmp_path)
    monkeypatch.setattr(launch_game, "available_port", lambda *a: None)
    monkeypatch.setattr(launch_game, "prepare_python", lambda *a, **kw: Path("python"))
    monkeypatch.setattr(demo_pack, "download", lambda *a, **kw: archive)
    monkeypatch.setattr(launch_game.os, "chdir", lambda *a: None)
    calls = []
    monkeypatch.setattr(launch_game.os, "execve", lambda *a: calls.append(a))
    launch_game.main(["demo"])
    assert calls[0][2]["DEMO_PACK_DIR"] == str(
        demo_pack.installed_path(tmp_path, source)
    )
    assert demo_pack.validate_installed(
        demo_pack.installed_path(tmp_path, source), source
    )


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("offline"),
        BadStatusLine("broken proxy"),
        IncompleteRead(b"partial"),
    ],
)
def test_unavailable_drive_fails_launch_without_server_or_fallback(
    tmp_path, monkeypatch, capsys, error
):
    _, source = build_zip(tmp_path)
    monkeypatch.setattr(launch_game, "ROOT", tmp_path)
    monkeypatch.setattr(launch_game, "available_port", lambda *a: None)
    monkeypatch.setattr(launch_game, "prepare_python", lambda *a, **kw: Path("python"))
    monkeypatch.setattr(
        drive_download, "build_opener", lambda *a, **kw: Opener([error])
    )
    monkeypatch.setattr(
        launch_game.os, "chdir", lambda *a: pytest.fail("No server preparation")
    )
    monkeypatch.setattr(
        launch_game.os, "execve", lambda *a: pytest.fail("No server without music")
    )
    with pytest.raises(SystemExit) as failure:
        launch_game.main(["demo"])
    assert failure.value.code == 1
    message = capsys.readouterr().err
    assert "Cannot launch:" in message and "tools/setup_demo_pack.py" in message
    assert not demo_pack.installed_path(tmp_path, source).exists()
    assert not list((tmp_path / "catalog/local/downloads").glob("*.zip"))
    assert not (tmp_path / "catalog/local/.drive-install.lock").exists()
