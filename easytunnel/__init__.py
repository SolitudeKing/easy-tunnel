"""EasyTunnel - a small graphical manager for OpenSSH local forwards."""

from .models import TunnelConfig, TunnelState
from .ssh_manager import SSHManager

__all__ = ["SSHManager", "TunnelConfig", "TunnelState"]
__version__ = "0.1.0"
