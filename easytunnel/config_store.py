from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from .models import LocalForward, TunnelConfig


class ConfigError(RuntimeError):
    pass


class ConfigStore:
    """JSON persistence with an atomic replace so a failed save keeps old data."""

    SCHEMA_VERSION = 2

    def __init__(self, path: Path, sample_key: Path | None = None) -> None:
        self.path = path
        self.sample_key = sample_key
        self._save_lock = threading.Lock()

    def load(self) -> list[TunnelConfig]:
        if not self.path.exists():
            return [self.example_tunnel()]
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("tunnels"), list):
                raise ConfigError("配置文件格式无效")
            version = data.get("schema_version", 1)
            if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                raise ConfigError(f"配置文件版本 {version!r} 无效")
            if version > self.SCHEMA_VERSION:
                raise ConfigError(f"配置文件版本 {version!r} 高于当前程序支持的版本")
            tunnels: list[TunnelConfig] = []
            seen_ids: set[str] = set()
            for index, raw in enumerate(data["tunnels"]):
                if not isinstance(raw, dict):
                    raise ConfigError(f"第 {index + 1} 条隧道配置格式无效")
                tunnel = TunnelConfig.from_dict(self._migrate_tunnel(raw, version))
                if not tunnel.id or tunnel.id in seen_ids:
                    tunnel.id = uuid4().hex
                seen_ids.add(tunnel.id)
                if tunnel.identity_file:
                    key_path = Path(tunnel.identity_file).expanduser()
                    if not key_path.is_absolute():
                        tunnel.identity_file = str((self.path.parent / key_path).resolve())
                errors = tunnel.validate(require_key_exists=False)
                if errors:
                    raise ConfigError(f"第 {index + 1} 条隧道配置无效：{errors[0]}")
                tunnels.append(tunnel)
            return tunnels
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ConfigError(f"无法读取配置：{exc}") from exc

    def save(self, tunnels: list[TunnelConfig]) -> None:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "tunnels": [tunnel.to_dict() for tunnel in tunnels],
        }
        temporary: Path | None = None
        try:
            with self._save_lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                document = json.dumps(payload, ensure_ascii=False, indent=2)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    handle.write(document)
                    handle.flush()
                    os.fsync(handle.fileno())
                    temporary = Path(handle.name)
                os.replace(temporary, self.path)
                temporary = None
        except (OSError, TypeError, UnicodeError) as exc:
            raise ConfigError(f"无法保存配置：{exc}") from exc
        finally:
            if temporary:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _migrate_tunnel(data: dict[str, object], version: int) -> dict[str, object]:
        if version >= 2:
            return dict(data)

        migrated = dict(data)
        tunnel_id = str(migrated.get("id") or uuid4().hex)
        migrated["id"] = tunnel_id
        migrated["forwards"] = [
            {
                "id": f"{tunnel_id}-forward-1",
                "name": str(migrated.get("name") or "主服务"),
                "service_type": str(migrated.get("service_type") or "tcp"),
                "bind_host": migrated.get("bind_host", "127.0.0.1"),
                "local_port": migrated.get("local_port"),
                "remote_host": migrated.get("remote_host"),
                "remote_port": migrated.get("remote_port"),
            }
        ]
        if migrated.get("keepalive_interval", 15) in {0, 15, "0", "15"}:
            migrated["keepalive_interval"] = 30
        for legacy_key in (
            "service_type",
            "bind_host",
            "local_port",
            "remote_host",
            "remote_port",
        ):
            migrated.pop(legacy_key, None)
        return migrated

    def example_tunnel(self) -> TunnelConfig:
        key = str(self.sample_key.resolve()) if self.sample_key and self.sample_key.is_file() else ""
        return TunnelConfig(
            name="办公室远程桌面",
            note="通过树莓派访问远程内网 Windows 桌面",
            ssh_host="pi.solitude.love",
            username="pi",
            ssh_port=22,
            identity_file=key,
            forwards=(
                LocalForward(
                    name="远程桌面",
                    service_type="rdp",
                    bind_host="127.0.0.1",
                    local_port=13389,
                    remote_host="192.168.3.88",
                    remote_port=3389,
                ),
            ),
        )
