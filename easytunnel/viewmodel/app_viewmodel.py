"""Presentation state and application actions for the EasyTunnel window."""

from __future__ import annotations

import ipaddress
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..config.paths import app_data_path, default_update_directory, project_sample_key
from ..model.runtime import RuntimeSnapshot
from ..model.tunnel import LocalForward, TunnelConfig
from ..model.update import UpdateError, UpdateInfo
from ..repository.tunnel_repository import ConfigError, TunnelRepository
from ..repository.update_repository import download_installer, fetch_latest_update
from ..service.platform_service import open_remote_desktop, open_web_service
from ..service.ssh_import_service import parse_ssh_command
from ..service.ssh_tunnel_service import SSHTunnelService
from ..service.update_service import is_packaged_windows_app, launch_installer
from .contracts import TunnelRepositoryPort, TunnelServicePort


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    """Outcome consumed by the view after a background update check."""

    update: UpdateInfo | None
    message: str
    is_error: bool = False


class ViewModelError(RuntimeError):
    """A user-facing application operation failed."""


class EasyTunnelViewModel:
    """Own mutable presentation state and coordinate repositories/services."""

    def __init__(
        self,
        *,
        repository: TunnelRepositoryPort | None = None,
        tunnel_service: TunnelServicePort | None = None,
        update_fetcher: Callable[[str], UpdateInfo | None] = fetch_latest_update,
        packaged_detector: Callable[[], bool] = is_packaged_windows_app,
        installer_downloader: Callable[[UpdateInfo, Path], Path] = download_installer,
        installer_launcher: Callable[[Path], None] = launch_installer,
        update_directory_provider: Callable[[], Path] = default_update_directory,
        remote_desktop_opener: Callable[[str], None] = open_remote_desktop,
        web_service_opener: Callable[[str], None] = open_web_service,
    ) -> None:
        self.repository = (
            repository
            if repository is not None
            else TunnelRepository(app_data_path(), project_sample_key())
        )
        self.tunnel_service = (
            tunnel_service if tunnel_service is not None else SSHTunnelService()
        )
        self._update_fetcher = update_fetcher
        self._packaged_detector = packaged_detector
        self._installer_downloader = installer_downloader
        self._installer_launcher = installer_launcher
        self._update_directory_provider = update_directory_provider
        self._remote_desktop_opener = remote_desktop_opener
        self._web_service_opener = web_service_opener

        self.load_error = ""
        try:
            self.configs = self.repository.load()
        except ConfigError as exc:
            self.configs = [self.repository.example_tunnel()]
            self.load_error = str(exc)
        self.tunnel_service.set_configs(self.configs)

        self.current_view = "tunnels"
        self.log_filter: str | None = None
        self.search_query = ""
        self.last_runtime_fingerprint: tuple[object, ...] = ()
        self.available_update: UpdateInfo | None = None
        self.checking_update = False
        self.update_status = ""

        self._toggle_lock = threading.Lock()
        self._toggle_targets: dict[str, bool] = {}
        self._toggle_workers: set[str] = set()

    @property
    def store(self) -> TunnelRepositoryPort:
        """Compatibility alias while callers migrate to ``repository``."""

        return self.repository

    @property
    def manager(self) -> TunnelServicePort:
        """Compatibility alias while callers migrate to ``tunnel_service``."""

        return self.tunnel_service

    @property
    def config_path(self) -> Path:
        return self.repository.path

    @property
    def ssh_executable(self) -> str:
        return self.tunnel_service.ssh_executable

    def snapshots(self) -> list[RuntimeSnapshot]:
        return self.tunnel_service.snapshots()

    def snapshot(self, tunnel_id: str) -> RuntimeSnapshot | None:
        return self.tunnel_service.snapshot(tunnel_id)

    def command_preview(self, config: TunnelConfig) -> str:
        return self.tunnel_service.command_preview(config)

    def set_current_view(self, view: str) -> None:
        if view not in {"tunnels", "logs", "settings"}:
            raise ValueError(f"未知视图：{view}")
        self.current_view = view

    def set_search_query(self, query: str) -> None:
        self.search_query = query

    def set_log_filter(self, tunnel_id: str | None) -> None:
        self.log_filter = tunnel_id

    def validate_config(self, config: TunnelConfig) -> list[str]:
        """Validate a form model against local safety and uniqueness rules."""

        errors = config.validate(require_key_exists=True)
        for forward in config.forwards:
            if not self.is_loopback(forward.bind_host):
                errors.append(
                    f"转发“{forward.name}”只允许绑定本机地址（例如 127.0.0.1 或 ::1）"
                )

        for existing in self.configs:
            if existing.id == config.id:
                continue
            existing_endpoints = {
                self.endpoint_key(forward.bind_host, forward.local_port)
                for forward in existing.forwards
            }
            duplicate = next(
                (
                    forward
                    for forward in config.forwards
                    if self.endpoint_key(forward.bind_host, forward.local_port)
                    in existing_endpoints
                ),
                None,
            )
            if duplicate:
                errors.append(
                    f"转发“{duplicate.name}”的本地端口与隧道“{existing.name}”重复"
                )
                break
        return errors

    def save_config(self, config: TunnelConfig, *, editing: bool) -> None:
        """Validate and atomically persist one created or edited tunnel."""

        errors = self.validate_config(config)
        if errors:
            raise ValueError(errors[0])
        new_configs = (
            [config if item.id == config.id else item for item in self.configs]
            if editing
            else [*self.configs, config]
        )
        try:
            self.repository.save(new_configs)
        except ConfigError as exc:
            raise ViewModelError(str(exc)) from exc
        self.configs = new_configs
        self.tunnel_service.set_configs(self.configs)
        self.last_runtime_fingerprint = ()

    def delete_config(self, tunnel_id: str) -> None:
        """Delete and persist a tunnel, restoring runtime state on failure."""

        previous = list(self.configs)
        self.configs = [item for item in self.configs if item.id != tunnel_id]
        self.tunnel_service.set_configs(self.configs)
        try:
            self.repository.save(self.configs)
        except ConfigError as exc:
            self.configs = previous
            self.tunnel_service.set_configs(previous)
            raise ViewModelError(str(exc)) from exc
        self.last_runtime_fingerprint = ()

    def persist(self) -> None:
        """Persist all current configurations."""

        try:
            self.repository.save(self.configs)
        except ConfigError as exc:
            raise ViewModelError(str(exc)) from exc

    def import_ssh_command(
        self,
        command_text: str,
        variable_text: str = "",
    ) -> TunnelConfig:
        """Convert safely parsed SSH text into an editable tunnel model."""

        command, inline_definitions = self.split_import_content(command_text)
        definitions = [
            line.strip()
            for line in (*inline_definitions, *variable_text.splitlines())
            if line.strip()
        ]
        imported = parse_ssh_command(command, definitions)
        identity_file = self.absolute_identity_path(imported.identity_file)
        forwards: list[LocalForward] = []
        for index, item in enumerate(imported.forwards, start=1):
            name, service_type = self.suggest_forward(item.remote_port, index)
            forwards.append(
                LocalForward(
                    name=name,
                    service_type=service_type,
                    bind_host=item.bind_host,
                    local_port=item.local_port,
                    remote_host=item.remote_host,
                    remote_port=item.remote_port,
                )
            )
        return TunnelConfig(
            name=f"{imported.username}@{imported.ssh_host}",
            note=f"从 SSH 命令导入，共 {len(forwards)} 条转发",
            ssh_host=imported.ssh_host,
            username=imported.username,
            ssh_port=imported.ssh_port,
            identity_file=identity_file,
            forwards=tuple(forwards),
            strict_host_key=(imported.option_value("StrictHostKeyChecking") == "yes"),
            connect_timeout=int(imported.option_value("ConnectTimeout") or 10),
            keepalive_interval=int(imported.option_value("ServerAliveInterval") or 30),
        )

    def open_forward(self, forward: LocalForward) -> str | None:
        """Open a known service, or return the endpoint for clipboard use."""

        endpoint = self.forward_endpoint(forward)
        if forward.service_type == "rdp":
            self._remote_desktop_opener(endpoint)
            return None
        if forward.service_type == "web":
            self._web_service_opener(endpoint)
            return None
        return endpoint

    def start_auto_connect(self) -> None:
        """Start configured automatic connections without blocking the UI."""

        for config in self.configs:
            if config.auto_connect:
                threading.Thread(
                    target=self.tunnel_service.start,
                    args=(config.id,),
                    daemon=True,
                ).start()

    def request_tunnel_state(self, tunnel_id: str, enabled: bool) -> None:
        """Coalesce rapid toggle requests into one background worker per tunnel."""

        with self._toggle_lock:
            self._toggle_targets[tunnel_id] = enabled
            if tunnel_id in self._toggle_workers:
                return
            self._toggle_workers.add(tunnel_id)
        threading.Thread(
            target=self._apply_tunnel_state,
            args=(tunnel_id,),
            daemon=True,
        ).start()
        self.last_runtime_fingerprint = ()

    def _apply_tunnel_state(self, tunnel_id: str) -> None:
        while True:
            with self._toggle_lock:
                target = self._toggle_targets.get(tunnel_id, False)
            if target:
                self.tunnel_service.start(tunnel_id)
            else:
                self.tunnel_service.stop(tunnel_id)
            with self._toggle_lock:
                if self._toggle_targets.get(tunnel_id, False) == target:
                    self._toggle_workers.discard(tunnel_id)
                    return

    def runtime_fingerprint(self) -> tuple[object, ...]:
        """Return the minimal runtime state that can affect visible controls."""

        return tuple(
            (
                item.config.id,
                item.state.value,
                item.pid,
                item.last_error,
                len(item.logs),
            )
            for item in self.tunnel_service.snapshots()
        )

    def default_update_message(self) -> str:
        if self._packaged_detector():
            return "启动时会自动检查 GitHub Release，也可手动检查。"
        return "自动安装仅适用于 Windows 安装版；当前为源码运行模式。"

    def is_packaged_app(self) -> bool:
        """Return whether in-app update installation is available."""

        return self._packaged_detector()

    def begin_update_check(self) -> bool:
        """Set checking state and report whether a network check should run."""

        if self.checking_update:
            return False
        if not self._packaged_detector():
            self.update_status = "自动安装仅适用于 Windows 安装版。"
            return False
        self.checking_update = True
        self.update_status = "正在检查更新…"
        return True

    def complete_update_check(self, current_version: str) -> UpdateCheckResult:
        """Fetch the latest release and normalize errors for presentation."""

        try:
            update = self._update_fetcher(current_version)
        except UpdateError as exc:
            self.update_status = f"检查更新失败：{exc}"
            return UpdateCheckResult(None, self.update_status, is_error=True)
        except Exception:
            LOGGER.exception("Unexpected update check failure")
            self.update_status = "检查更新失败：发生意外错误，请稍后重试。"
            return UpdateCheckResult(None, self.update_status, is_error=True)
        else:
            self.available_update = update
            if update is None:
                self.update_status = "当前已是最新稳定版本。"
            else:
                self.update_status = f"发现新版本 {update.version}。"
            return UpdateCheckResult(update, self.update_status)
        finally:
            self.checking_update = False

    def install_update(self, update: UpdateInfo) -> None:
        """Download, verify, and launch an update, then stop all tunnels."""

        try:
            installer = self._installer_downloader(
                update,
                self._update_directory_provider(),
            )
            self._installer_launcher(installer)
        except UpdateError as exc:
            raise ViewModelError(str(exc)) from exc
        self.tunnel_service.shutdown()

    def shutdown(self) -> None:
        self.tunnel_service.shutdown()

    @staticmethod
    def endpoint_key(host: str, port: int) -> tuple[str, int]:
        value = host.strip().strip("[]").lower()
        if value == "localhost":
            value = "127.0.0.1"
        try:
            value = ipaddress.ip_address(value).compressed
        except ValueError:
            pass
        return value, port

    @staticmethod
    def is_loopback(host: str) -> bool:
        value = host.strip().strip("[]")
        if value.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(value).is_loopback
        except ValueError:
            return False

    @staticmethod
    def forward_endpoint(forward: LocalForward) -> str:
        host = forward.bind_host.strip("[]")
        if ":" in host:
            return f"[{host}]:{forward.local_port}"
        return f"{host}:{forward.local_port}"

    @staticmethod
    def split_import_content(text: str) -> tuple[str, tuple[str, ...]]:
        definitions: list[str] = []
        command_lines: list[str] = []
        command_started = False
        for line in text.splitlines():
            stripped = line.strip()
            name, separator, _ = stripped.partition("=")
            is_variable = bool(
                separator
                and name
                and (name[0].isalpha() or name[0] == "_")
                and all(char.isalnum() or char == "_" for char in name)
            )
            if not command_started and (not stripped or is_variable):
                if is_variable:
                    definitions.append(stripped)
                continue
            command_started = True
            command_lines.append(line)
        return "\n".join(command_lines).strip(), tuple(definitions)

    @staticmethod
    def suggest_forward(remote_port: int, index: int) -> tuple[str, str]:
        suggestions = {
            3389: ("远程桌面", "rdp"),
            3306: ("MySQL", "tcp"),
            3369: ("MySQL", "tcp"),
            6379: ("Redis", "tcp"),
            6380: ("Redis", "tcp"),
            80: ("Web 服务", "web"),
            443: ("Web 服务", "web"),
            9000: ("MinIO API", "web"),
            9001: ("MinIO 控制台", "web"),
        }
        return suggestions.get(remote_port, (f"转发 {index}", "tcp"))

    @staticmethod
    def absolute_identity_path(value: str) -> str:
        normalized = value.replace("/", "\\")
        if os.name == "nt" and normalized.startswith("\\\\"):
            raise ValueError("私钥文件不允许使用网络共享或 Windows 设备路径")
        path = Path(value).expanduser()
        return str(path if path.is_absolute() else path.absolute())
