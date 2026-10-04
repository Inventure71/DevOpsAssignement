"""Python environment setup and local signing-key validation."""

import subprocess
import sys
import json
import re

from tools.launch_support import LaunchError

RUNTIME_MODULES = ("fastapi", "uvicorn", "jwt", "cryptography")


def venv_python(root):
    windows = root / ".venv/Scripts/python.exe"
    return windows if windows.is_file() else root / ".venv/bin/python"


def probe_python(python, requirements):
    expected = []
    try:
        for line in requirements.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(
                r"([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^\s]+)", line
            )
            if not match:
                raise LaunchError(
                    "The root requirements.txt must contain exact package version pins."
                )
            expected.append(match.groups())
    except OSError:
        raise LaunchError(
            "The root requirements.txt is missing or unreadable."
        ) from None
    probe = (
        "import importlib, importlib.metadata, json, sys; errors=[]; "
        "\nfor name in " + repr(RUNTIME_MODULES) + ":"
        "\n try: importlib.import_module(name)"
        "\n except Exception: errors.append(name)"
        "\nfor name, required in " + repr(expected) + ":"
        "\n try: installed=importlib.metadata.version(name)"
        "\n except importlib.metadata.PackageNotFoundError: installed=None"
        "\n if installed != required: errors.append(name+'=='+required)"
        "\nprint(json.dumps({'version':list(sys.version_info[:2]), 'missing':errors}))"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", probe], capture_output=True, text=True, check=True
        )
        status = json.loads(result.stdout)
        if status["version"] < [3, 12]:
            raise LaunchError(
                "The project .venv needs Python 3.12 or newer; recreate it with a supported Python."
            )
        return status["missing"]
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        raise LaunchError(
            "The project Python environment is unusable; recreate .venv with Python 3.12 or newer."
        ) from None


def prepare_python(root, *, check):
    """Check the existing environment or prepare it for launch."""
    python = venv_python(root)
    if not python.is_file():
        if check:
            raise LaunchError(
                "No project .venv found. Run this launcher without --check to create it and install requirements.txt."
            )
        print(
            "Creating .venv with Python "
            + str(sys.version_info.major)
            + "."
            + str(sys.version_info.minor)
            + "...",
            flush=True,
        )
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(root / ".venv")], check=True
            )
        except (OSError, subprocess.CalledProcessError):
            raise LaunchError(
                "Could not create .venv. Install Python 3.12+ with venv support and retry."
            ) from None
        python = venv_python(root)
    missing = probe_python(python, root / "requirements.txt")
    if missing:
        if check:
            raise LaunchError(
                "Missing/unusable dependencies: "
                + ", ".join(missing)
                + ". Run without --check to install requirements.txt."
            )
        print(
            "Installing root requirements.txt (first setup needs internet or a local pip package cache)...",
            flush=True,
        )
        try:
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    str(root / "requirements.txt"),
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError):
            raise LaunchError(
                "Dependency installation failed. Resolve the pip error above and retry; Demo needs no provider keys."
            ) from None
        if probe_python(python, root / "requirements.txt"):
            raise LaunchError(
                "Dependencies remain unavailable after installation; check the pip output."
            )
    return python


def check_real_signing_key(python, environment):
    """Validate the local Apple signing key."""
    script = (
        "import os; from pathlib import Path; "
        "from cryptography.hazmat.primitives.serialization import load_pem_private_key; "
        "from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey, SECP256R1; "
        "key=load_pem_private_key(Path(os.environ['APPLE_PRIVATE_KEY_PATH']).read_bytes(), password=None); "
        "assert isinstance(key, EllipticCurvePrivateKey) and isinstance(key.curve, SECP256R1)"
    )
    try:
        subprocess.run(
            [str(python), "-c", script],
            env=environment,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        raise LaunchError(
            "APPLE_PRIVATE_KEY_PATH must contain a valid, unencrypted Apple ES256 (.p8) signing key."
        ) from None
