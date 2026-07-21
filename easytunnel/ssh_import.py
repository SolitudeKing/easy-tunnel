"""Compatibility imports for the pre-MVVM SSH import module."""

from .model.ssh_import import ImportedForward, ImportedOption, ImportedSSHCommand
from .service.ssh_import_service import (
    SSHImportError,
    parse_ssh_command,
    parse_variable_definitions,
)

__all__ = [
    "ImportedForward",
    "ImportedOption",
    "ImportedSSHCommand",
    "SSHImportError",
    "parse_ssh_command",
    "parse_variable_definitions",
]
