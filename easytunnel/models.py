from __future__ import annotations

import ipaddress
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


def _forward_host(host: str) -> str:
    value = host.strip().strip("[]")
    return f"[{value}]" if ":" in value else value


def _endpoint_key(host: str, port: int) -> tuple[str, int]:
    value = host.strip().strip("[]").lower()
    if value == "localhost":
        value = "127.0.0.1"
    try:
        value = ipaddress.ip_address(value).compressed
    except ValueError:
        pass
    return value, port


def _split_forward_spec(spec: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    bracket_depth = 0
    for char in spec.strip():
        if char == "[":
            bracket_depth += 1
            continue
        if char == "]":
            if bracket_depth == 0:
                raise ValueError("转发规则中的 IPv6 方括号不匹配")
            bracket_depth -= 1
            continue
        if char == ":" and bracket_depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if bracket_depth:
        raise ValueError("转发规则中的 IPv6 方括号不匹配")
    parts.append("".join(current))
    return parts


@dataclass(frozen=True, slots=True)
class LocalForward:
    """One local port mapping carried by an SSH session."""

    name: str
    bind_host: str
    local_port: int
    remote_host: str
    remote_port: int
    service_type: str = "tcp"
    id: str = field(default_factory=lambda: uuid4().hex)

    def validate(self, *, label: str = "转发") -> list[str]:
        errors: list[str] = []
        for field_label, value in (
            ("名称", self.name),
            ("本地绑定地址", self.bind_host),
            ("目标主机", self.remote_host),
        ):
            text = str(value).strip()
            display_label = f"{label}{field_label}"
            if not text:
                errors.append(f"{display_label}不能为空")
            elif any(ord(char) < 32 for char in text):
                errors.append(f"{display_label}包含无效控制字符")
            elif field_label != "名称" and any(char.isspace() for char in text):
                errors.append(f"{display_label}不能包含空格")
            elif field_label == "目标主机" and text.startswith("-"):
                errors.append(f"{display_label}不能以 '-' 开头")

        for field_label, value in (
            ("本地端口", self.local_port),
            ("目标端口", self.remote_port),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
                errors.append(f"{label}{field_label}必须是 1 到 65535 之间的整数")

        if self.service_type not in {"rdp", "web", "tcp"}:
            errors.append(f"{label}服务类型无效")
        if not self.id:
            errors.append(f"{label} ID 不能为空")
        return errors

    def to_ssh_spec(self) -> str:
        return (
            f"{_forward_host(self.bind_host)}:{self.local_port}:"
            f"{_forward_host(self.remote_host)}:{self.remote_port}"
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_spec(
        cls,
        spec: str,
        *,
        name: str = "端口转发",
        service_type: str = "tcp",
        forward_id: str | None = None,
    ) -> "LocalForward":
        parts = _split_forward_spec(spec)
        if len(parts) == 3:
            bind_host = "127.0.0.1"
            local_port, remote_host, remote_port = parts
        elif len(parts) == 4:
            bind_host, local_port, remote_host, remote_port = parts
        else:
            raise ValueError("转发规则必须是 [本地地址:]本地端口:目标地址:目标端口")
        if not all(part.strip() for part in (bind_host, local_port, remote_host, remote_port)):
            raise ValueError("转发规则不能包含空字段")
        try:
            local_port_value = int(local_port)
            remote_port_value = int(remote_port)
        except ValueError as exc:
            raise ValueError("转发规则中的端口必须是整数") from exc
        return cls(
            id=forward_id or uuid4().hex,
            name=name,
            service_type=service_type,
            bind_host=bind_host.strip(),
            local_port=local_port_value,
            remote_host=remote_host.strip(),
            remote_port=remote_port_value,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalForward":
        allowed = {item.name for item in fields(cls)}
        clean = {key: value for key, value in data.items() if key in allowed}
        for key in ("id", "name", "service_type", "bind_host", "remote_host"):
            if key in clean and not isinstance(clean[key], str):
                clean[key] = "" if clean[key] is None else str(clean[key])
        for key in ("local_port", "remote_port"):
            value = clean.get(key)
            if isinstance(value, str) and value.strip().isdigit():
                clean[key] = int(value)
        return cls(**clean)


@dataclass(slots=True)
class TunnelConfig:
    name: str
    ssh_host: str
    username: str
    forwards: tuple[LocalForward, ...]
    id: str = field(default_factory=lambda: uuid4().hex)
    note: str = ""
    ssh_port: int = 22
    identity_file: str = ""
    strict_host_key: bool = False
    auto_connect: bool = False
    connect_timeout: int = 10
    keepalive_interval: int = 30

    def validate(self, *, require_key_exists: bool = False) -> list[str]:
        errors: list[str] = []
        for label, value in (
            ("隧道名称", self.name),
            ("SSH 主机", self.ssh_host),
            ("SSH 用户名", self.username),
        ):
            text = str(value).strip()
            if not text:
                errors.append(f"{label}不能为空")
            elif any(ord(char) < 32 for char in text):
                errors.append(f"{label}包含无效控制字符")
            elif label in {"SSH 主机", "SSH 用户名"} and text.startswith("-"):
                errors.append(f"{label}不能以 '-' 开头")
            elif label == "SSH 主机" and any(char.isspace() for char in text):
                errors.append(f"{label}不能包含空格")

        if any(char.isspace() for char in self.username) or "@" in self.username:
            errors.append("SSH 用户名不能包含空格或 @")
        if "@" in self.ssh_host:
            errors.append("SSH 主机不能包含 @")

        if isinstance(self.ssh_port, bool) or not isinstance(self.ssh_port, int) or not 1 <= self.ssh_port <= 65535:
            errors.append("SSH 端口必须是 1 到 65535 之间的整数")

        if not self.forwards:
            errors.append("至少需要一条本地端口转发")
        seen_endpoints: set[tuple[str, int]] = set()
        seen_ids: set[str] = set()
        for index, forward in enumerate(self.forwards, start=1):
            errors.extend(forward.validate(label=f"第 {index} 条转发的"))
            endpoint = _endpoint_key(forward.bind_host, forward.local_port)
            if endpoint in seen_endpoints:
                errors.append(f"第 {index} 条转发的本地监听地址与同组规则重复")
            seen_endpoints.add(endpoint)
            if forward.id in seen_ids:
                errors.append(f"第 {index} 条转发的 ID 与同组规则重复")
            seen_ids.add(forward.id)

        if (
            isinstance(self.connect_timeout, bool)
            or not isinstance(self.connect_timeout, int)
            or not 1 <= self.connect_timeout <= 120
        ):
            errors.append("连接超时必须是 1 到 120 秒")
        if (
            isinstance(self.keepalive_interval, bool)
            or not isinstance(self.keepalive_interval, int)
            or not 1 <= self.keepalive_interval <= 3600
        ):
            errors.append("保活间隔必须是 1 到 3600 秒")

        if self.identity_file:
            key_path = Path(self.identity_file).expanduser()
            if require_key_exists and not key_path.is_file():
                errors.append(f"私钥文件不存在：{key_path}")
        elif require_key_exists:
            errors.append("请选择 SSH 私钥文件")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TunnelConfig":
        allowed = {item.name for item in fields(cls)}
        clean = {key: value for key, value in data.items() if key in allowed}
        raw_forwards = clean.get("forwards", ())
        if not isinstance(raw_forwards, (list, tuple)):
            raise TypeError("forwards must be a JSON array")
        clean["forwards"] = tuple(
            item if isinstance(item, LocalForward) else LocalForward.from_dict(item)
            for item in raw_forwards
            if isinstance(item, (dict, LocalForward))
        )
        if len(clean["forwards"]) != len(raw_forwards):
            raise TypeError("each forward must be a JSON object")
        for key in ("id", "name", "note", "ssh_host", "username", "identity_file"):
            if key in clean and not isinstance(clean[key], str):
                clean[key] = "" if clean[key] is None else str(clean[key])
        for key in ("ssh_port", "connect_timeout", "keepalive_interval"):
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
