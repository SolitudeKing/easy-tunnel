"""Update metadata shared by update repositories and services."""

from __future__ import annotations

from dataclasses import dataclass

from packaging.version import Version


class UpdateError(RuntimeError):
    """Raised when an update cannot be safely discovered or installed."""


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    """A verified installer available in a newer GitHub release."""

    version: Version
    installer_name: str
    installer_url: str
    sha256: str
    installer_size: int | None
    release_url: str
    release_notes: str
