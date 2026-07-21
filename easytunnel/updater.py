"""Compatibility imports for the pre-MVVM update module."""

from .model.update import UpdateError, UpdateInfo
from .repository.update_repository import (
    DOWNLOAD_CHUNK_SIZE,
    GITHUB_LATEST_RELEASE_PAGE_URL,
    GITHUB_LATEST_RELEASE_URL,
    GITHUB_RELEASE_DOWNLOAD_URL_TEMPLATE,
    INSTALLER_NAME_TEMPLATE,
    MAX_CHECKSUM_SIZE,
    MAX_INSTALLER_SIZE,
    download_installer,
    fetch_latest_update,
    parse_latest_release,
)
from .service.update_service import (
    default_update_directory,
    is_packaged_windows_app,
    is_packaged_windows_runtime as _is_packaged_windows_runtime,
    launch_installer,
)

__all__ = [
    "DOWNLOAD_CHUNK_SIZE",
    "GITHUB_LATEST_RELEASE_PAGE_URL",
    "GITHUB_LATEST_RELEASE_URL",
    "GITHUB_RELEASE_DOWNLOAD_URL_TEMPLATE",
    "INSTALLER_NAME_TEMPLATE",
    "MAX_CHECKSUM_SIZE",
    "MAX_INSTALLER_SIZE",
    "UpdateError",
    "UpdateInfo",
    "_is_packaged_windows_runtime",
    "default_update_directory",
    "download_installer",
    "fetch_latest_update",
    "is_packaged_windows_app",
    "launch_installer",
    "parse_latest_release",
]
