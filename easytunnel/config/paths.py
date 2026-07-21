"""Filesystem and packaged-asset locations used by the application."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_LOGO_ASSET = "images/easytunnel-logo.png"
APP_WINDOW_ICON_ASSET = "icons/easytunnel.ico"


def runtime_assets_directory() -> Path:
    """Locate assets in source, a wheel install, or a bundled executable."""

    override = os.environ.get("FLET_ASSETS_DIR")
    if override:
        return Path(override).expanduser().resolve()

    source_assets = Path(__file__).resolve().parents[2] / "assets"
    candidates = [
        source_assets,
        Path(sys.prefix) / "share" / "easytunnel" / "assets",
        Path(sys.executable).resolve().parent / "assets",
        Path.cwd() / "assets",
    ]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.insert(0, Path(bundle_root) / "assets")

    for candidate in candidates:
        if (candidate / APP_LOGO_ASSET).is_file() and (
            candidate / APP_WINDOW_ICON_ASSET
        ).is_file():
            return candidate.resolve()
    return source_assets


def app_data_path() -> Path:
    """Return the tunnel configuration path, honoring an explicit override."""

    override = os.environ.get("EASYTUNNEL_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "EasyTunnel" / "tunnels.json"


def project_sample_key() -> Path | None:
    """Return the development-only sample key when it exists."""

    candidate = Path(__file__).resolve().parents[2] / "pi-server"
    return candidate if candidate.is_file() else None


def default_update_directory() -> Path:
    """Return the user-local directory for verified update downloads."""

    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "EasyTunnel" / "updates"
