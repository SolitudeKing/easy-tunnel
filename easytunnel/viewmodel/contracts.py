"""Structural contracts injected into the application ViewModel."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..model.runtime import RuntimeSnapshot
from ..model.tunnel import TunnelConfig


class TunnelRepositoryPort(Protocol):
    path: Path

    def load(self) -> list[TunnelConfig]: ...

    def save(self, tunnels: list[TunnelConfig]) -> None: ...

    def example_tunnel(self) -> TunnelConfig: ...


class TunnelServicePort(Protocol):
    ssh_executable: str

    def set_configs(self, configs: list[TunnelConfig]) -> None: ...

    def snapshots(self) -> list[RuntimeSnapshot]: ...

    def snapshot(self, tunnel_id: str) -> RuntimeSnapshot | None: ...

    def command_preview(self, config: TunnelConfig) -> str: ...

    def start(self, tunnel_id: str) -> bool: ...

    def stop(self, tunnel_id: str) -> bool: ...

    def shutdown(self) -> None: ...
