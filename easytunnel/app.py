"""Compatibility entry point for the MVVM Flet view."""

import flet as ft

from .component.widget.theme import (
    AMBER,
    AMBER_SOFT,
    BG,
    BG_SECONDARY,
    BORDER,
    BORDER_STRONG,
    DISABLED,
    FORM_ACCENT,
    FORM_ACCENT_ACTIVE,
    FORM_ACCENT_HOVER,
    FORM_ACCENT_LIGHT,
    FORM_ACCENT_SOFT,
    FORM_BG,
    FORM_BG_SECONDARY,
    FORM_BORDER,
    FORM_BORDER_STRONG,
    FORM_CARD,
    FORM_DANGER,
    FORM_DANGER_SOFT,
    FORM_HOVER,
    FORM_INSET,
    FORM_MUTED,
    FORM_SUCCESS,
    FORM_SURFACE,
    FORM_TEXT,
    FORM_TEXT_SECONDARY,
    GREEN,
    GREEN_SOFT,
    HOVER,
    INSET,
    MUTED,
    PRIMARY,
    PRIMARY_ACTIVE,
    PRIMARY_HOVER,
    PRIMARY_LIGHT,
    PRIMARY_SOFT,
    RED,
    RED_ACTIVE,
    RED_HOVER,
    RED_SOFT,
    SIDEBAR,
    SURFACE,
    SURFACE_MUTED,
    TEXT,
    TEXT_SECONDARY,
)
from .config.paths import (
    APP_LOGO_ASSET,
    APP_WINDOW_ICON_ASSET,
    app_data_path as _app_data_path,
    default_update_directory,
    project_sample_key as _project_sample_key,
)
from .model.runtime import RuntimeSnapshot
from .model.tunnel import LocalForward, TunnelConfig, TunnelState
from .model.update import UpdateError, UpdateInfo
from .repository.tunnel_repository import (
    ConfigError,
    ConfigStore,
    TunnelRepository,
)
from .repository.update_repository import download_installer, fetch_latest_update
from .service.platform_service import open_remote_desktop, open_web_service
from .service.ssh_import_service import SSHImportError, parse_ssh_command
from .service.ssh_tunnel_service import SSHManager, SSHTunnelService
from .service.update_service import is_packaged_windows_app, launch_installer
from .view.app_view import EasyTunnelApp
from .viewmodel.app_viewmodel import EasyTunnelViewModel


def create_view_model() -> EasyTunnelViewModel:
    """Compose production repositories and services for the desktop app."""

    return EasyTunnelViewModel(
        repository=TunnelRepository(_app_data_path(), _project_sample_key()),
        tunnel_service=SSHTunnelService(),
        update_fetcher=fetch_latest_update,
        packaged_detector=is_packaged_windows_app,
        installer_downloader=download_installer,
        installer_launcher=launch_installer,
        update_directory_provider=default_update_directory,
        remote_desktop_opener=open_remote_desktop,
        web_service_opener=open_web_service,
    )


def main(page: ft.Page) -> None:
    """Mount the application with production MVVM dependencies."""

    EasyTunnelApp(page, create_view_model()).mount()


__all__ = [
    "APP_LOGO_ASSET",
    "APP_WINDOW_ICON_ASSET",
    "AMBER",
    "AMBER_SOFT",
    "BG",
    "BG_SECONDARY",
    "BORDER",
    "BORDER_STRONG",
    "ConfigError",
    "ConfigStore",
    "DISABLED",
    "EasyTunnelApp",
    "FORM_ACCENT",
    "FORM_ACCENT_ACTIVE",
    "FORM_ACCENT_HOVER",
    "FORM_ACCENT_LIGHT",
    "FORM_ACCENT_SOFT",
    "FORM_BG",
    "FORM_BG_SECONDARY",
    "FORM_BORDER",
    "FORM_BORDER_STRONG",
    "FORM_CARD",
    "FORM_DANGER",
    "FORM_DANGER_SOFT",
    "FORM_HOVER",
    "FORM_INSET",
    "FORM_MUTED",
    "FORM_SUCCESS",
    "FORM_SURFACE",
    "FORM_TEXT",
    "FORM_TEXT_SECONDARY",
    "GREEN",
    "GREEN_SOFT",
    "HOVER",
    "INSET",
    "LocalForward",
    "MUTED",
    "PRIMARY",
    "PRIMARY_ACTIVE",
    "PRIMARY_HOVER",
    "PRIMARY_LIGHT",
    "PRIMARY_SOFT",
    "RED",
    "RED_ACTIVE",
    "RED_HOVER",
    "RED_SOFT",
    "RuntimeSnapshot",
    "SSHImportError",
    "SSHManager",
    "SIDEBAR",
    "SURFACE",
    "SURFACE_MUTED",
    "TEXT",
    "TEXT_SECONDARY",
    "TunnelConfig",
    "TunnelState",
    "UpdateError",
    "UpdateInfo",
    "create_view_model",
    "default_update_directory",
    "download_installer",
    "fetch_latest_update",
    "is_packaged_windows_app",
    "launch_installer",
    "main",
    "parse_ssh_command",
]
