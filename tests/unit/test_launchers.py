"""Launch boundaries, setup failure handling, and real subprocess preflights."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from backend.core.config import Config
from tools import launch_game as entry
from tools import launch_environment as launch
from tools import launch_runtime as runtime
from tools import launch_support as network

ROOT = Path(__file__).resolve().parents[2]


def options(**values):
    defaults = dict(port=None, data_dir=None, playtest=False, demo_pack=None)
    defaults.update(values)
    return argparse.Namespace(**defaults)


def make_pack(path):
    assets = path / "assets"
    assets.mkdir(parents=True)
    (assets / "credits.html").write_text("Music credits")
    entries = []
    prefix = "/static/demo/local/"
    for number in range(16):
        asset = f"clip-{number}.mp3"
        (assets / asset).write_bytes(b"fixture-media")
        entries.append(
            dict(
                id=f"clip-{number}",
                pool_kind="personal" if number < 15 else "decoy",
                isrc=None,
                title=f"Song {number}",
                artist="Artist",
                artists=[dict(artist_key="demo:artist", name="Artist")],
                preview_url=prefix + asset,
                artwork_url=None,
            )
        )
    (path / "demo_catalog.json").write_text(json.dumps(entries))
    return entries


@pytest.fixture
def project(tmp_path):
    from tests.unit.test_demo_pack_install import build_zip
    from tools.demo_pack import install

    archive, _ = build_zip(tmp_path)
    install(tmp_path, archive=archive)
    (tmp_path / "requirements.txt").write_text((ROOT / "requirements.txt").read_text())
    return tmp_path


@pytest.fixture
def real_settings(tmp_path):
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    key = tmp_path / "Apple key.p8"
    key.write_bytes(
        ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return dict(
        SPOTIFY_CLIENT_ID="test-client",
        APPLE_TEAM_ID="test-team",
        APPLE_KEY_ID="test-key",
        APPLE_PRIVATE_KEY_PATH=str(key),
        APP_PUBLIC_URL="https://classroom.example",
        SPOTIFY_REDIRECT_URI="https://classroom.example/api/music/spotify/callback",
    )


@pytest.fixture
def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_demo_ignores_broken_dotenv_and_inherited_provider_transport_settings(
    project, monkeypatch
):
    (project / ".env").write_text("not valid shell or dotenv at all")
    poisoned = {key: "invalid" for key in launch.APPLICATION_KEYS}
    poisoned["PATH"] = os.environ.get("PATH", "")
    environment, notes, description = launch.build_environment(
        project, "demo", options(), poisoned
    )
    assert environment["GAME_MODE"] == "demo"
    assert environment["COOKIE_SECURE"] == "false"
    assert environment["APP_PUBLIC_URL"] == ""
    assert environment["PORT"] == "8000"
    assert environment["PLAYTEST_MODE"] == "false"
    assert environment["DATA_DIR"] == str(project / "data/demo")
    assert not any(
        key in environment for key in ("SPOTIFY_CLIENT_ID", "APPLE_PRIVATE_KEY_PATH")
    )
    assert not notes and description == "local Demo pack (100 clips)"
    assert Path(environment["DEMO_PACK_DIR"]).is_dir()
    monkeypatch.setattr(os, "environ", environment)
    config = Config.from_env()
    assert config.cookie_secure is False and config.spotify_client_id == ""
    assert not config.public_url and config.port == 8000


def test_explicit_demo_options_are_independent_of_the_shell_directory(
    project, monkeypatch
):
    monkeypatch.chdir(project.parent)
    environment, _, _ = launch.build_environment(
        project, "demo", options(port=8123, data_dir="qa data", playtest=True), {}
    )
    assert environment["PORT"] == "8123"
    assert environment["DATA_DIR"] == str(project / "qa data")
    assert environment["PLAYTEST_MODE"] == "true"
    assert not (project / "qa data").exists()


@pytest.mark.parametrize("mode", ["demo", "real"])
def test_pinned_pack_is_selected_and_corrupt_media_stops_launch(
    project, real_settings, mode
):
    from tools.demo_pack import installed_path, load_source

    selected = installed_path(project, load_source(project))
    settings = real_settings if mode == "real" else {}
    environment, notes, description = launch.build_environment(
        project, mode, options(), settings
    )
    assert environment["DEMO_PACK_DIR"] == str(selected)
    assert not notes and "local Demo pack (100 clips)" in description
    catalog = (selected / "demo_catalog.json").read_bytes()
    (selected / "assets/clips/fixture-3.m4a").unlink()
    with pytest.raises((OSError, ValueError, launch.LaunchError)):
        launch.build_environment(project, mode, options(), settings)
    assert (selected / "demo_catalog.json").read_bytes() == catalog


@pytest.mark.parametrize("mode", ["demo", "real"])
def test_explicit_incomplete_pack_fails_instead_of_silently_changing_music(
    project, real_settings, mode
):
    with pytest.raises(launch.LaunchError, match="incomplete"):
        launch.build_environment(
            project,
            mode,
            options(demo_pack="missing"),
            real_settings if mode == "real" else {},
        )


def test_real_launch_accepts_explicit_demo_pack_and_cli_overrides_configured_pack(
    project, real_settings
):
    selected = project / "custom-pack"
    make_pack(selected)
    settings = dict(real_settings, DEMO_PACK_DIR="broken-configured-pack")
    environment, notes, description = launch.build_environment(
        project, "real", options(demo_pack="custom-pack"), settings
    )
    assert environment["GAME_MODE"] == "normal"
    assert environment["DEMO_PACK_DIR"] == str(selected)
    assert not notes and "Demo: local Demo pack" in description


def test_real_launch_retains_the_same_pinned_demo_pack(project, real_settings):
    from tools.demo_pack import installed_path, load_source

    environment, notes, description = launch.build_environment(
        project, "real", options(), real_settings
    )
    assert environment["DEMO_PACK_DIR"] == str(
        installed_path(project, load_source(project))
    )
    assert not notes and "Demo: local Demo pack (100 clips)" in description


@pytest.mark.parametrize(
    "damage", ["traversal", "empty", "credits", "metadata", "too-small"]
)
def test_pack_validation_catches_a_playable_catalogs_dependencies(project, damage):
    local = project / "catalog/local"
    entries = make_pack(local)
    if damage == "traversal":
        entries[0]["preview_url"] = "/static/demo/local/%2e%2e/%2e%2e/outside.mp3"
    elif damage == "empty":
        (local / "assets/clip-0.mp3").write_bytes(b"")
    elif damage == "credits":
        (local / "assets/credits.html").unlink()
    elif damage == "metadata":
        entries[0]["artists"] = []
    else:
        entries = entries[:4]
    (local / "demo_catalog.json").write_text(json.dumps(entries))
    with pytest.raises(launch.LaunchError):
        launch.validate_demo_pack(local)


def test_dotenv_is_literal_and_never_executes_shell_content(tmp_path):
    marker = tmp_path / "executed"
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f'SPOTIFY_CLIENT_ID="$(touch {marker})"\n'
        "export APPLE_TEAM_ID='Team # 1' # comment\n"
        "APPLE_KEY_ID=key\nAPPLE_STOREFRONT=\n"
        "PATH=/untrusted/path\n"
    )
    settings = launch.read_dotenv(dotenv)
    assert settings["SPOTIFY_CLIENT_ID"] == f"$(touch {marker})"
    assert settings["APPLE_TEAM_ID"] == "Team # 1"
    assert settings["APPLE_STOREFRONT"] == ""
    assert "PATH" not in settings and not marker.exists()


@pytest.mark.parametrize(
    "line",
    ["source otherfile", "APPLE_KEY_ID='unterminated", "APPLE_KEY_ID=unquoted spaces"],
)
def test_malformed_real_dotenv_has_actionable_line_error(tmp_path, line):
    path = tmp_path / ".env"
    path.write_text(line)
    with pytest.raises(launch.LaunchError, match="line 1"):
        launch.read_dotenv(path)


def test_real_loads_dotenv_but_explicit_environment_and_cli_win(project, real_settings):
    (project / ".env").write_text(
        "\n".join(f'{key}="{value}"' for key, value in real_settings.items())
        + "\nGAME_MODE=demo\nPORT=8100\nCOOKIE_SECURE=false\n"
    )
    environment, notes, description = launch.build_environment(
        project,
        "real",
        options(port=8110, data_dir="qa"),
        {"SPOTIFY_CLIENT_ID": "override"},
    )
    assert (
        environment["GAME_MODE"] == "normal" and environment["COOKIE_SECURE"] == "true"
    )
    assert (
        environment["PORT"] == "8110" and environment["SPOTIFY_CLIENT_ID"] == "override"
    )
    assert environment["DATA_DIR"] == str(project / "qa")
    assert not notes and "Spotify" in description


@pytest.mark.parametrize(
    "public",
    [
        "http://192.168.1.80:8000",
        "https://127.0.0.1",
        "https://0.0.0.0",
        "https://game.example/path",
        "https://user:password@game.example",
        "https://game.example:broken",
    ],
)
def test_real_rejects_non_shared_https_origins(project, real_settings, public):
    real_settings["APP_PUBLIC_URL"] = public
    with pytest.raises(launch.LaunchError, match="APP_PUBLIC_URL"):
        launch.build_environment(project, "real", options(), real_settings)


def test_real_callback_missing_keys_and_missing_signing_file_fail_before_setup(
    project, real_settings
):
    invalid = dict(real_settings, SPOTIFY_REDIRECT_URI="http://127.0.0.1:8000/callback")
    with pytest.raises(launch.LaunchError, match="SPOTIFY_REDIRECT_URI"):
        launch.build_environment(project, "real", options(), invalid)
    invalid = dict(real_settings, APPLE_TEAM_ID="")
    with pytest.raises(launch.LaunchError, match="APPLE_TEAM_ID"):
        launch.build_environment(project, "real", options(), invalid)
    invalid = dict(real_settings, APPLE_PRIVATE_KEY_PATH="missing.p8")
    with pytest.raises(launch.LaunchError, match="APPLE_PRIVATE_KEY_PATH"):
        launch.build_environment(project, "real", options(), invalid)


def test_signing_key_validation_accepts_real_es256_and_rejects_invalid_content(
    real_settings, tmp_path
):
    runtime.check_real_signing_key(sys.executable, dict(os.environ, **real_settings))
    bad = tmp_path / "bad.p8"
    bad.write_text("invalid key")
    with pytest.raises(launch.LaunchError, match="ES256"):
        runtime.check_real_signing_key(
            sys.executable,
            {**os.environ, **real_settings, "APPLE_PRIVATE_KEY_PATH": str(bad)},
        )


@pytest.mark.parametrize("port", [-1, 0, 65536, "invalid"])
def test_invalid_port_never_reaches_server_setup(project, port):
    with pytest.raises(launch.LaunchError, match="PORT"):
        launch.build_environment(project, "demo", options(port=port), {})


def test_used_port_has_actionable_error_and_does_not_stop_its_owner():
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(launch.LaunchError, match="choose --port"):
            network.available_port(port)
        assert listener.fileno() >= 0


def test_check_with_missing_venv_does_not_create_files_or_run_pip(project, monkeypatch):
    calls = []
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw: calls.append(a))
    with pytest.raises(launch.LaunchError, match="No project .venv"):
        runtime.prepare_python(project, check=True)
    assert calls == [] and not (project / ".venv").exists()


def test_windows_python_layout_is_recognized(project):
    python = project / ".venv/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    assert runtime.venv_python(project) == python


def test_existing_ready_venv_does_not_reinstall(project, monkeypatch):
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(runtime, "probe_python", lambda p, manifest: [])
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda *a, **kw: pytest.fail("No setup should run")
    )
    assert runtime.prepare_python(project, check=False) == python


def test_first_setup_creates_venv_then_installs_only_root_requirements(
    project, monkeypatch
):
    python = project / ".venv/bin/python"
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[2] == "venv":
            python.parent.mkdir(parents=True)
            python.touch()
        return subprocess.CompletedProcess(command, 0)

    missing = iter([["fastapi"], []])
    monkeypatch.setattr(runtime.subprocess, "run", run)
    monkeypatch.setattr(runtime, "probe_python", lambda p, manifest: next(missing))
    assert runtime.prepare_python(project, check=False) == python
    assert calls == [
        [sys.executable, "-m", "venv", str(project / ".venv")],
        [str(python), "-m", "pip", "install", "-r", str(project / "requirements.txt")],
    ]


def test_missing_dependencies_check_never_installs(project, monkeypatch):
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(runtime, "probe_python", lambda p, manifest: ["uvicorn"])
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda *a, **kw: pytest.fail("No pip during --check")
    )
    with pytest.raises(launch.LaunchError, match="uvicorn"):
        runtime.prepare_python(project, check=True)


def test_dependency_probe_checks_exact_root_pins_even_when_runtime_imports_work(
    tmp_path,
):
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("uvicorn==9999.0\nPyJWT[crypto]==2.10.1\n")
    missing = runtime.probe_python(sys.executable, manifest)
    assert "uvicorn==9999.0" in missing
    assert "PyJWT==2.10.1" not in missing


def test_dependency_probe_rejects_old_project_python(project, monkeypatch):
    monkeypatch.setattr(
        runtime.subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(
            a, 0, stdout=json.dumps(dict(version=[3, 11], missing=[]))
        ),
    )
    with pytest.raises(launch.LaunchError, match="Python 3.12"):
        runtime.probe_python(Path("old-python"), project / "requirements.txt")


def test_failed_install_is_actionable_and_never_runs_server(project, monkeypatch):
    python = project / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(runtime, "probe_python", lambda p, manifest: ["fastapi"])

    def failing_pip(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(runtime.subprocess, "run", failing_pip)
    with pytest.raises(launch.LaunchError, match="Dependency installation failed"):
        runtime.prepare_python(project, check=False)


def test_startup_replaces_process_with_selected_environment(
    project, monkeypatch, free_port
):
    monkeypatch.setattr(entry, "ROOT", project)
    monkeypatch.setattr(entry, "prepare_python", lambda *a, **kw: Path(sys.executable))
    monkeypatch.setattr(entry, "print_addresses", lambda *a: None)
    calls = []
    monkeypatch.setattr(entry.os, "chdir", lambda path: calls.append(("cwd", path)))
    monkeypatch.setattr(
        entry.os,
        "execve",
        lambda program, args, env: calls.append((program, args, env)),
    )
    entry.main(["demo", "--port", str(free_port), "--data-dir", "qa", "--playtest"])
    assert calls[0] == ("cwd", project)
    program, args, environment = calls[1]
    assert args == [program, "-m", "backend"]
    assert (
        environment["GAME_MODE"] == "demo" and environment["COOKIE_SECURE"] == "false"
    )
    assert environment["PLAYTEST_MODE"] == "true"
    assert environment["DATA_DIR"] == str(project / "qa")


def test_subprocess_demo_preflight_from_outside_repo_is_read_only_and_ignores_keys(
    tmp_path, free_port
):
    environment = dict(os.environ)
    environment.update({key: "broken" for key in launch.APPLICATION_KEYS})
    pack = tmp_path / "media"
    make_pack(pack)
    data = tmp_path / "not-created"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/launch_game.py"),
            "demo",
            "--check",
            "--demo-pack",
            str(pack),
            "--port",
            str(free_port),
            "--data-dir",
            str(data),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert f"http://127.0.0.1:{free_port}/" in result.stdout
    assert "no API keys" in result.stdout and "0.0.0.0" not in result.stdout
    assert "https://" not in result.stdout and "Preflight passed" in result.stdout
    assert not data.exists()


def test_subprocess_real_preflight_uses_supplied_settings_and_never_leaks_secrets(
    tmp_path, real_settings, free_port
):
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in launch.APPLICATION_KEYS
    }
    environment.update(real_settings)
    pack = tmp_path / "media"
    make_pack(pack)
    data = tmp_path / "not-created"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/launch_game.py"),
            "real",
            "--check",
            "--demo-pack",
            str(pack),
            "--port",
            str(free_port),
            "--data-dir",
            str(data),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (
        "https://classroom.example/" in result.stdout
        and "Spotify and Demo available" in result.stdout
    )
    private_key = Path(real_settings["APPLE_PRIVATE_KEY_PATH"]).read_text()
    assert private_key not in result.stdout + result.stderr
    assert not data.exists()


def test_subprocess_real_missing_credentials_does_not_install_or_touch_data(
    tmp_path, real_settings, free_port
):
    environment = {**os.environ, **real_settings, "APPLE_TEAM_ID": ""}
    data = tmp_path / "not-created"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/launch_game.py"),
            "real",
            "--check",
            "--port",
            str(free_port),
            "--data-dir",
            str(data),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1 and "APPLE_TEAM_ID" in result.stderr
    assert "Installing" not in result.stdout and not data.exists()


@pytest.mark.skipif(
    os.name == "nt",
    reason="Bash wrappers are for macOS/Linux; Windows uses the Python entry point",
)
def test_bash_demo_wrapper_from_outside_repo_uses_portable_entry(tmp_path, free_port):
    pack = tmp_path / "media"
    make_pack(pack)
    data = tmp_path / "not-created"
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "tools/run_demo.sh"),
            "--check",
            "--demo-pack",
            str(pack),
            "--port",
            str(free_port),
            "--data-dir",
            str(data),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert f"http://127.0.0.1:{free_port}/" in result.stdout
    assert "Preflight passed" in result.stdout and not data.exists()


def test_demo_address_output_uses_lan_and_reports_unknown_lan(monkeypatch, capsys):
    environment = dict(PORT="8011", PLAYTEST_MODE="false", DATA_DIR="test-data")
    monkeypatch.setattr(network, "discover_lan_host", lambda: "192.168.10.5")
    network.print_addresses("demo", environment, "local Demo pack (100 clips)")
    output = capsys.readouterr().out
    assert "http://127.0.0.1:8011/" in output
    assert "http://192.168.10.5:8011/" in output and "0.0.0.0" not in output
    monkeypatch.setattr(network, "discover_lan_host", lambda: None)
    network.print_addresses("demo", environment, "local Demo pack (100 clips)")
    assert "automatic LAN detection was unavailable" in capsys.readouterr().out
