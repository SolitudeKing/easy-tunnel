"""Runtime snapshots exposed by the SSH tunnel service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .tunnel import TunnelConfig, TunnelState


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
