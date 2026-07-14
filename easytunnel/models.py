from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4


class TunnelState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(slots=True)
class TunnelConfig:
    name: str
    ssh_host: str
    username: str
    local_port: int
    remote_host: str
    remote_port: int
    id: str = field(default_factory=lambda: uuid4().hex)
    note: str = ""
    service_type: str = "rdp"
    ssh_port: int = 22
    identity_file: str = ""
    bind_host: str = "127.0.0.1"
    strict_host_key: bool = False
    auto_connect: bool = False
    connect_timeout: int = 10
    keepalive_interval: int = 15

    def validate(self, *, require_key_exists: bool = False) -> list[str]:
        errors: list[str] = []
        for label, value in (
            ("隧道名称", self.name),
            ("SSH 主机", self.ssh_host),
            ("SSH 用户名", self.username),
            ("目标主机", self.remote_host),
            ("本地绑定地址", self.bind_host),
        ):
            text = str(value).strip()
            if not text:
                errors.append(f"{label}不能为空")
            elif any(ord(char) < 32 for char in text):
                errors.append(f"{label}包含无效控制字符")
            elif label in {"SSH 主机", "SSH 用户名"} and text.startswith("-"):
                errors.append(f"{label}不能以 '-' 开头")
            elif label in {"SSH 主机", "目标主机", "本地绑定地址"} and any(
                char.isspace() for char in text
            ):
                errors.append(f"{label}不能包含空格")

        if any(char.isspace() for char in self.username) or "@" in self.username:
            errors.append("SSH 用户名不能包含空格或 @")
        if "@" in self.ssh_host:
            errors.append("SSH 主机不能包含 @")

        for label, value in (
            ("SSH 端口", self.ssh_port),
            ("本地端口", self.local_port),
            ("目标端口", self.remote_port),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
                errors.append(f"{label}必须是 1 到 65535 之间的整数")

        if (
            isinstance(self.connect_timeout, bool)
            or not isinstance(self.connect_timeout, int)
            or not 1 <= self.connect_timeout <= 120
        ):
            errors.append("连接超时必须是 1 到 120 秒")
        if (
            isinstance(self.keepalive_interval, bool)
            or not isinstance(self.keepalive_interval, int)
            or not 0 <= self.keepalive_interval <= 3600
        ):
            errors.append("保活间隔必须是 0 到 3600 秒")

        if self.identity_file:
            key_path = Path(self.identity_file).expanduser()
            if require_key_exists and not key_path.is_file():
                errors.append(f"私钥文件不存在：{key_path}")
        elif require_key_exists:
            errors.append("请选择 SSH 私钥文件")

        if self.service_type not in {"rdp", "web", "tcp"}:
            errors.append("服务类型无效")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TunnelConfig":
        allowed = {item.name for item in fields(cls)}
        clean = {key: value for key, value in data.items() if key in allowed}
        for key in (
            "id",
            "name",
            "note",
            "service_type",
            "ssh_host",
            "username",
            "identity_file",
            "bind_host",
            "remote_host",
        ):
            if key in clean and not isinstance(clean[key], str):
                clean[key] = "" if clean[key] is None else str(clean[key])
        for key in ("ssh_port", "local_port", "remote_port", "connect_timeout", "keepalive_interval"):
            value = clean.get(key)
            if isinstance(value, str) and value.strip().isdigit():
                clean[key] = int(value)
        for key in ("strict_host_key", "auto_connect"):
            if key in clean and not isinstance(clean[key], bool):
                raise TypeError(f"{key} must be a JSON boolean")
        return cls(**clean)


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: datetime
    level: str
    message: str


@dataclass(slots=True)
class RuntimeSnapshot:
    config: TunnelConfig
    state: TunnelState
    pid: int | None
    started_at: datetime | None
    last_error: str
    logs: tuple[LogEntry, ...]

    @property
    def uptime_seconds(self) -> int:
        if not self.started_at or self.state != TunnelState.CONNECTED:
            return 0
        return max(0, int((datetime.now() - self.started_at).total_seconds()))
