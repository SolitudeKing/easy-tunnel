"""Safe update discovery and installer download support for EasyTunnel."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version


GITHUB_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/SolitudeKing/easy-tunnel/releases/latest"
)
INSTALLER_NAME_TEMPLATE = "EasyTunnel-Setup-{version}.exe"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class UpdateError(RuntimeError):
    """Raised when an update cannot be safely discovered or installed."""


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    """A verified installer available in a newer GitHub release.

    Attributes:
        version: The newer application version.
        installer_name: Expected Windows installer file name.
        installer_url: Direct HTTPS URL for the installer release asset.
        sha256: Expected SHA-256 digest without the ``sha256:`` prefix.
        installer_size: Expected size of the installer in bytes.
        release_url: Browser URL for the release notes.
        release_notes: Release notes supplied by GitHub.
    """

    version: Version
    installer_name: str
    installer_url: str
    sha256: str
    installer_size: int
    release_url: str
    release_notes: str


def is_packaged_windows_app() -> bool:
    """Return whether the application is running as a Flet Windows package."""
    return os.name == "nt" and bool(os.environ.get("FLET_ASSETS_DIR"))


def fetch_latest_update(current_version: str, *, timeout_seconds: float = 8.0) -> UpdateInfo | None:
    """Fetch a newer stable Windows installer from GitHub Releases.

    Args:
        current_version: Installed application version.
        timeout_seconds: Network timeout for the GitHub API request.

    Returns:
        A verified update description, or ``None`` when no newer stable version
        is available.

    Raises:
        UpdateError: If the release data is unavailable or unsafe to install.
    """
    request = Request(
        GITHUB_LATEST_RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"EasyTunnel/{current_version}",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            document = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(f"无法检查更新：GitHub 返回 HTTP {exc.code}") from exc
    except (OSError, TimeoutError, URLError, json.JSONDecodeError) as exc:
        raise UpdateError(f"无法检查更新：{exc}") from exc

    if not isinstance(document, dict):
        raise UpdateError("无法检查更新：GitHub 返回了无效的数据")
    return parse_latest_release(document, current_version)


def parse_latest_release(release: dict[str, object], current_version: str) -> UpdateInfo | None:
    """Validate a GitHub release document and extract its Windows installer.

    Args:
        release: Decoded GitHub release JSON document.
        current_version: Installed application version.

    Returns:
        A verified update description, or ``None`` if it is not a newer stable
        release.

    Raises:
        UpdateError: If a newer release lacks a valid installer or digest.
    """
    if release.get("draft") is True or release.get("prerelease") is True:
        return None

    tag_name = _required_text(release, "tag_name")
    if not tag_name.startswith("v"):
        raise UpdateError("无法检查更新：发布标签必须以 v 开头")
    try:
        latest_version = Version(tag_name[1:])
        installed_version = Version(current_version)
    except InvalidVersion as exc:
        raise UpdateError(f"无法检查更新：版本号无效（{exc}）") from exc
    if latest_version <= installed_version:
        return None

    expected_name = INSTALLER_NAME_TEMPLATE.format(version=latest_version)
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("新版本缺少发布资产列表")
    for item in assets:
        if not isinstance(item, dict) or item.get("name") != expected_name:
            continue
        installer_url = _required_text(item, "browser_download_url")
        digest = _required_text(item, "digest")
        checksum = digest.removeprefix("sha256:")
        if not digest.startswith("sha256:") or len(checksum) != 64:
            raise UpdateError("新版本安装包缺少有效的 SHA-256 校验值")
        try:
            bytes.fromhex(checksum)
        except ValueError as exc:
            raise UpdateError("新版本安装包缺少有效的 SHA-256 校验值") from exc
        size = item.get("size")
        if not isinstance(size, int) or size <= 0:
            raise UpdateError("新版本安装包大小无效")
        return UpdateInfo(
            version=latest_version,
            installer_name=expected_name,
            installer_url=installer_url,
            sha256=checksum,
            installer_size=size,
            release_url=_required_text(release, "html_url"),
            release_notes=str(release.get("body") or ""),
        )

    raise UpdateError(f"新版本未提供 Windows 安装包：{expected_name}")


def download_installer(update: UpdateInfo, destination_dir: Path) -> Path:
    """Download and SHA-256 verify an installer before making it available.

    Args:
        update: Validated release asset metadata.
        destination_dir: Local directory for the verified installer.

    Returns:
        The path of the verified installer.

    Raises:
        UpdateError: If the installer cannot be downloaded or validated.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / update.installer_name
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination_dir,
        prefix=f".{update.installer_name}.",
        suffix=".part",
    )
    temporary = Path(temporary_name)
    digest = hashlib.sha256()
    downloaded_size = 0
    try:
        with os.fdopen(descriptor, "wb") as handle:
            request = Request(
                update.installer_url,
                headers={"User-Agent": "EasyTunnel updater"},
            )
            with urlopen(request, timeout=30) as response:
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    downloaded_size += len(chunk)
                    digest.update(chunk)
                    handle.write(chunk)
        if downloaded_size != update.installer_size:
            raise UpdateError("安装包下载不完整，已取消更新")
        if digest.hexdigest().lower() != update.sha256.lower():
            raise UpdateError("安装包 SHA-256 校验失败，已取消更新")
        os.replace(temporary, destination)
        return destination
    except (OSError, TimeoutError, URLError) as exc:
        raise UpdateError(f"无法下载安装包：{exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def launch_installer(installer: Path) -> None:
    """Launch a verified Windows installer without invoking a shell.

    Args:
        installer: Verified installer path.

    Raises:
        UpdateError: If the installer cannot be started.
    """
    if os.name != "nt":
        raise UpdateError("自动安装仅支持 Windows 安装版")
    try:
        subprocess.Popen([str(installer)], close_fds=True)
    except OSError as exc:
        raise UpdateError(f"无法启动安装程序：{exc}") from exc


def default_update_directory() -> Path:
    """Return the user-local directory used for verified update downloads."""
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "EasyTunnel" / "updates"


def _required_text(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise UpdateError(f"GitHub 发布数据缺少有效字段：{key}")
    return value
