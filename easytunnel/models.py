"""Compatibility imports for the pre-MVVM model module."""

from .model.runtime import LogEntry, RuntimeSnapshot
from .model.tunnel import LocalForward, TunnelConfig, TunnelState

__all__ = [
    "LocalForward",
    "LogEntry",
    "RuntimeSnapshot",
    "TunnelConfig",
    "TunnelState",
]
