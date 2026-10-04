"""Install an immutable Demo pack independently of credentials and game data."""

from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

from tools.drive_download import download, sha256, verify_archive
from tools.demo_pack_validation import validate_demo_pack
from backend.core.paths import pinned_demo_pack_path

MAX_EXPANDED_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024


def load_source(root):
    path = root / "catalog/demo_pack_source.json"
    if not path.is_file():
        return None
    source = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or any(
        not isinstance(source.get(key), str)
        for key in ("pack", "file_id", "sha256", "manifest_sha256")
    ):
        raise ValueError("Invalid pinned Demo pack source")
    if (
        source.get("schema_version") != 1
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source.get("pack", ""))
        or not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", source.get("file_id", ""))
        or any(
            not re.fullmatch(r"[a-f0-9]{64}", source.get(key, ""))
            for key in ("sha256", "manifest_sha256")
        )
        or not isinstance(source.get("bytes"), int)
        or not 0 < source["bytes"] <= MAX_EXPANDED_BYTES
        or source.get("song_count") != 100
        or source.get("pools") != {"personal": 80, "decoy": 20}
    ):
        raise ValueError("Invalid pinned Demo pack source")
    return source


def installed_path(root, source):
    return pinned_demo_pack_path(root, source)


def safe_member(name):
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in name.split("/"))
        or name != str(path)
    ):
        raise ValueError("Unsafe path in Demo pack")
    return path


def read_manifest(data, source):
    if hashlib.sha256(data).hexdigest() != source["manifest_sha256"]:
        raise ValueError("Demo pack manifest SHA-256 disagrees with the pinned pack")
    manifest = json.loads(data)
    if any(manifest.get(key) != source[key] for key in ("pack", "song_count", "pools")):
        raise ValueError("Demo pack manifest describes another pack")
    files = manifest.get("files")
    if (
        manifest.get("schema_version") != 1
        or not isinstance(files, dict)
        or len(files) != 103
    ):
        raise ValueError("Demo pack inventory is incomplete")
    if (
        not {"demo_catalog.json", "provenance.json", "assets/credits.html"}
        <= files.keys()
    ):
        raise ValueError("Demo pack metadata is missing")
    if len({name.casefold() for name in files}) != len(files):
        raise ValueError("Demo pack contains conflicting filenames")
    for name, info in files.items():
        safe_member(name)
        if (
            not isinstance(info, dict)
            or not isinstance(info.get("bytes"), int)
            or not 0 < info["bytes"] <= MAX_FILE_BYTES
            or not re.fullmatch(r"[a-f0-9]{64}", info.get("sha256", ""))
        ):
            raise ValueError("Invalid Demo pack inventory entry")
    return files


def validate_installed(pack, source):
    """Entirely offline; detect missing or changed media before selecting a pack."""
    files = read_manifest((pack / "pack-manifest.json").read_bytes(), source)
    for name, expected in files.items():
        path = pack / name
        if not path.resolve().is_relative_to(pack.resolve()) or path.is_symlink():
            raise ValueError("Demo pack asset escapes its directory")
        if (
            path.stat().st_size != expected["bytes"]
            or sha256(path) != expected["sha256"]
        ):
            raise ValueError(f"Installed Demo asset failed verification: {name}")
    # Reuse the launcher's actual catalog/schema/asset validation, not another schema.
    if validate_demo_pack(pack) != source["song_count"]:
        raise ValueError("Demo catalog song count disagrees with its manifest")
    entries = json.loads((pack / "demo_catalog.json").read_text(encoding="utf-8"))
    if dict(Counter(entry["pool_kind"] for entry in entries)) != source["pools"]:
        raise ValueError("Demo pool counts disagree with its manifest")
    return pack


def extract_verified(archive, destination, source):
    verify_archive(archive, source)
    with zipfile.ZipFile(archive) as zipped:
        entries = zipped.infolist()
        names = [entry.filename for entry in entries]
        if (
            len(entries) != 104
            or len(set(names)) != len(names)
            or sum(entry.file_size for entry in entries) > MAX_EXPANDED_BYTES
        ):
            raise ValueError("Unexpected Demo ZIP inventory or expanded size")
        for entry in entries:
            safe_member(entry.filename)
            kind = stat.S_IFMT(entry.external_attr >> 16)
            if (
                entry.is_dir()
                or kind not in (0, stat.S_IFREG)
                or not 0 < entry.file_size <= MAX_FILE_BYTES
                or entry.flag_bits & 1
            ):
                raise ValueError("Demo ZIP contains an unsupported file")
        files = read_manifest(zipped.read("pack-manifest.json"), source)
        if set(names) != set(files) | {"pack-manifest.json"}:
            raise ValueError("Demo ZIP files disagree with its manifest")
        for entry in entries:
            if (
                entry.filename in files
                and entry.file_size != files[entry.filename]["bytes"]
            ):
                raise ValueError("Demo ZIP file size disagrees with its manifest")
            target = destination / entry.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(entry) as original, target.open("xb") as output:
                while chunk := original.read(1024 * 1024):
                    output.write(chunk)
    return validate_installed(destination, source)


@contextmanager
def installation_lock(root):
    local = root / "catalog/local"
    local.mkdir(parents=True, exist_ok=True)
    lock = local / ".drive-install.lock"
    try:
        stream = lock.open("x")
    except FileExistsError:
        raise ValueError(
            "Another Demo installation owns catalog/local/.drive-install.lock; "
            "wait for it, or remove the lock only after an interrupted installer stops"
        ) from None
    try:
        with stream:
            yield
    finally:
        lock.unlink(missing_ok=True)


def install(root, *, archive=None, progress=print):
    source = load_source(root)
    if source is None:
        raise ValueError("The pinned Demo pack source is missing")
    target = installed_path(root, source)
    if target.exists():
        return validate_installed(target, source)
    with installation_lock(root):
        if target.exists():
            return validate_installed(target, source)
        archive = (
            Path(archive)
            if archive
            else download(
                source,
                root / "catalog/local/downloads" / (source["sha256"] + ".zip"),
                progress=progress,
            )
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".install-", dir=target.parent
        ) as temporary:
            staged = Path(temporary) / "pack"
            staged.mkdir()
            extract_verified(archive, staged, source)
            staged.replace(target)
    return target
