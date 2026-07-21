"""Compatibility imports for the pre-MVVM SSH tunnel manager module."""

from .service.ssh_tunnel_service import SSHManager, _powershell_join

__all__ = ["SSHManager", "_powershell_join"]
