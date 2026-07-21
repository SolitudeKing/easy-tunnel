"""Small platform integrations kept outside the Flet view."""

from __future__ import annotations

import os
import subprocess
import webbrowser


def open_remote_desktop(endpoint: str) -> None:
    """Open a local endpoint with the Windows Remote Desktop client."""

    if os.name != "nt":
        raise RuntimeError("自动打开远程桌面目前仅支持 Windows")
    subprocess.Popen(["mstsc", f"/v:{endpoint}"], shell=False)


def open_web_service(endpoint: str) -> None:
    """Open a local HTTP endpoint in the default browser."""

    webbrowser.open(f"http://{endpoint}")
