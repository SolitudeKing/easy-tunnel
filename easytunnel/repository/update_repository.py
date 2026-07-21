"""Safe update discovery and installer download support for EasyTunnel."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from ..model.update import UpdateError, UpdateInfo


GITHUB_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/SolitudeKing/easy-tunnel/releases/latest"
)
GITHUB_LATEST_RELEASE_PAGE_URL = (
    "https://github.com/SolitudeKing/easy-tunnel/releases/latest"
)
GITHUB_RELEASE_DOWNLOAD_URL_TEMPLATE = (
    "https://github.com/SolitudeKing/easy-tunnel/releases/download/"
    "v{version}/{asset_name}"
)
INSTALLER_NAME_TEMPLATE = "EasyTunnel-Setup-{version}.exe"
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
MAX_CHECKSUM_SIZE = 4096
MAX_INSTALLER_SIZE = 512 * 1024 * 1024


def fetch_latest_update(
    current_version: str,
    *,
    timeout_seconds: float = 8.0,
) -> UpdateInfo | None:
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
        if exc.code in {403, 429}:
            return _fetch_latest_update_from_release_page(
                current_version,
                timeout_seconds=timeout_seconds,
            )
        raise UpdateError(f"无法检查更新：GitHub 返回 HTTP {exc.code}") from exc
    except (OSError, TimeoutError, URLError, json.JSONDecodeError) as exc:
        raise UpdateError(f"无法检查更新：{exc}") from exc

    if not isinstance(document, dict):
        raise UpdateError("无法检查更新：GitHub 返回了无效的数据")
    return parse_latest_release(document, current_version)


def parse_latest_release(
    release: dict[str, object],
    current_version: str,
) -> UpdateInfo | None:
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
        if not digest.startswith("sha256:"):
            raise UpdateError("新版本安装包缺少有效的 SHA-256 校验值")
        checksum = _validate_checksum(digest.removeprefix("sha256:"))
        size = item.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise UpdateError("新版本安装包大小无效")
        if size > MAX_INSTALLER_SIZE:
            raise UpdateError("新版本安装包超过最大允许大小")
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


def _fetch_latest_update_from_release_page(
    current_version: str,
    *,
    timeout_seconds: float,
) -> UpdateInfo | None:
    """Discover an update without using the rate-limited GitHub API."""
    headers = {"User-Agent": f"EasyTunnel/{current_version}"}
    latest_request = Request(
        GITHUB_LATEST_RELEASE_PAGE_URL,
        headers=headers,
        method="HEAD",
    )
    try:
        with urlopen(latest_request, timeout=timeout_seconds) as response:
            release_url = response.geturl()
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise UpdateError(f"无法检查更新：GitHub 返回 HTTP {exc.code}") from exc
    except (OSError, TimeoutError, URLError) as exc:
        raise UpdateError(f"无法检查更新：{exc}") from exc

    latest_version = _release_version_from_url(release_url)
    try:
        installed_version = Version(current_version)
    except InvalidVersion as exc:
        raise UpdateError(f"无法检查更新：版本号无效（{exc}）") from exc
    if latest_version <= installed_version:
        return None

    installer_name = INSTALLER_NAME_TEMPLATE.format(version=latest_version)
    installer_url = GITHUB_RELEASE_DOWNLOAD_URL_TEMPLATE.format(
        version=latest_version,
        asset_name=installer_name,
    )
    checksum_request = Request(
        f"{installer_url}.sha256",
        headers=headers,
    )
    try:
        with urlopen(checksum_request, timeout=timeout_seconds) as response:
            checksum_document = response.read(MAX_CHECKSUM_SIZE + 1)
    except HTTPError as exc:
        raise UpdateError(f"新版本缺少 SHA-256 校验文件（HTTP {exc.code}）") from exc
    except (OSError, TimeoutError, URLError) as exc:
        raise UpdateError(f"无法获取新版本校验文件：{exc}") from exc
    if len(checksum_document) > MAX_CHECKSUM_SIZE:
        raise UpdateError("新版本 SHA-256 校验文件过大")

    return UpdateInfo(
        version=latest_version,
        installer_name=installer_name,
        installer_url=installer_url,
        sha256=_parse_checksum_document(checksum_document, installer_name),
        installer_size=None,
        release_url=release_url,
        release_notes="",
    )


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
    destination = destination_dir / update.installer_name
    descriptor: int | None = None
    temporary: Path | None = None
    digest = hashlib.sha256()
    downloaded_size = 0
    expected_size = update.installer_size
    try:
        if expected_size is not None and expected_size > MAX_INSTALLER_SIZE:
            raise UpdateError("安装包超过最大允许大小，已取消更新")
        destination_dir.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination_dir,
            prefix=f".{update.installer_name}.",
            suffix=".part",
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            request = Request(
                update.installer_url,
                headers={"User-Agent": "EasyTunnel updater"},
            )
            with urlopen(request, timeout=30) as response:
                if expected_size is None:
                    expected_size = _response_content_length(response)
                if expected_size is not None and expected_size > MAX_INSTALLER_SIZE:
                    raise UpdateError("安装包超过最大允许大小，已取消更新")
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    downloaded_size += len(chunk)
                    if downloaded_size > MAX_INSTALLER_SIZE:
                        raise UpdateError("安装包超过最大允许大小，已取消更新")
                    if expected_size is not None and downloaded_size > expected_size:
                        raise UpdateError("安装包大小与发布信息不符，已取消更新")
                    digest.update(chunk)
                    handle.write(chunk)
        if expected_size is not None and downloaded_size != expected_size:
            raise UpdateError("安装包下载不完整，已取消更新")
        if digest.hexdigest().lower() != update.sha256.lower():
            raise UpdateError("安装包 SHA-256 校验失败，已取消更新")
        os.replace(temporary, destination)
        return destination
    except UpdateError:
        raise
    except (OSError, TimeoutError, URLError) as exc:
        raise UpdateError(f"无法下载安装包：{exc}") from exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _required_text(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise UpdateError(f"GitHub 发布数据缺少有效字段：{key}")
    return value


def _release_version_from_url(release_url: str) -> Version:
    parsed = urlparse(release_url)
    path_prefix = "/SolitudeKing/easy-tunnel/releases/tag/"
    path = unquote(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or not path.startswith(path_prefix)
    ):
        raise UpdateError("无法检查更新：GitHub 最新版本地址无效")
    tag_name = path.removeprefix(path_prefix)
    if not tag_name.startswith("v") or "/" in tag_name:
        raise UpdateError("无法检查更新：发布标签必须以 v 开头")
    try:
        return Version(tag_name[1:])
    except InvalidVersion as exc:
        raise UpdateError(f"无法检查更新：版本号无效（{exc}）") from exc


def _parse_checksum_document(document: bytes, installer_name: str) -> str:
    try:
        fields = document.decode("ascii").strip().split()
    except UnicodeDecodeError as exc:
        raise UpdateError("新版本 SHA-256 校验文件格式无效") from exc
    if len(fields) != 2 or fields[1].removeprefix("*") != installer_name:
        raise UpdateError("新版本 SHA-256 校验文件与安装包不匹配")
    return _validate_checksum(fields[0])


def _validate_checksum(checksum: str) -> str:
    if re.fullmatch(r"[0-9a-fA-F]{64}", checksum) is None:
        raise UpdateError("新版本安装包缺少有效的 SHA-256 校验值")
    return checksum.lower()


def _response_content_length(response: object) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get("Content-Length")
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return size if size > 0 else None
