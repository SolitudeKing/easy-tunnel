"""Structured values produced by safe SSH command import."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImportedForward:
    """A validated local TCP forwarding rule from one ``-L`` argument."""

    bind_host: str
    local_port: int
    remote_host: str
    remote_port: int


@dataclass(frozen=True, slots=True)
class ImportedOption:
    """A validated, canonical OpenSSH ``-o`` option."""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class ImportedSSHCommand:
    """Structured data extracted from a local-forward-only SSH command."""

    executable: str
    identity_file: str
    ssh_port: int
    username: str
    ssh_host: str
    forwards: tuple[ImportedForward, ...]
    options: tuple[ImportedOption, ...]
    no_remote_command: bool
    disable_tty: bool
    config_file_disabled: bool

    def option_value(self, name: str) -> str | None:
        """Return a validated option value using a case-insensitive lookup."""

        wanted = name.casefold()
        for option in self.options:
            if option.name.casefold() == wanted:
                return option.value
        return None
