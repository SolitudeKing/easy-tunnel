"""Platform operations for applying a verified update."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from ..config.paths import default_update_directory
from ..model.update import UpdateError


def is_packaged_windows_app() -> bool:
    """Return whether the application is running as a Flet Windows package."""

    return is_packaged_windows_runtime(os.name, os.environ)


def is_packaged_windows_runtime(
    os_name: str,
    environment: Mapping[str, str],
) -> bool:
    """Evaluate packaged-runtime markers without reading global state."""

    return (
        os_name == "nt"
        and environment.get("FLET_PLATFORM") == "windows"
        and bool(environment.get("FLET_APP_STORAGE_DATA"))
    )


def launch_installer(installer: Path) -> None:
    """Launch a verified Windows installer without invoking a shell."""

    if os.name != "nt":
        raise UpdateError("自动安装仅支持 Windows 安装版")
    try:
        subprocess.Popen([str(installer)], close_fds=True)
    except OSError as exc:
        raise UpdateError(f"无法启动安装程序：{exc}") from exc


__all__ = [
    "default_update_directory",
    "is_packaged_windows_app",
    "is_packaged_windows_runtime",
    "launch_installer",
]
