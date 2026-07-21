"""EasyTunnel - a small graphical manager for OpenSSH local forwards."""

from .model.tunnel import LocalForward, TunnelConfig, TunnelState
from .repository.tunnel_repository import TunnelRepository
from .service.ssh_tunnel_service import SSHManager, SSHTunnelService

__all__ = [
    "LocalForward",
    "SSHManager",
    "SSHTunnelService",
    "TunnelConfig",
    "TunnelRepository",
    "TunnelState",
]
__version__ = "0.1.3"
