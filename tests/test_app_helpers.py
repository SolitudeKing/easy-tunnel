import os
from pathlib import Path

import flet as ft
import pytest

from easytunnel.app import EasyTunnelApp
from easytunnel.models import LocalForward


def test_loopback_validation_accepts_ipv4_ipv6_and_localhost() -> None:
    assert EasyTunnelApp._is_loopback("127.0.0.1")
    assert EasyTunnelApp._is_loopback("127.8.9.10")
    assert EasyTunnelApp._is_loopback("::1")
    assert EasyTunnelApp._is_loopback("[::1]")
    assert EasyTunnelApp._is_loopback("localhost")


def test_loopback_validation_rejects_lan_and_wildcards() -> None:
    assert not EasyTunnelApp._is_loopback("0.0.0.0")
    assert not EasyTunnelApp._is_loopback("::")
    assert not EasyTunnelApp._is_loopback("192.168.1.20")
    assert not EasyTunnelApp._is_loopback("host.example.com")


def test_identity_paths_are_made_absolute_without_accepting_windows_shares() -> None:
    expected = str((Path.cwd() / "keys" / "pi-server").absolute())
    assert EasyTunnelApp._absolute_identity_path(r"keys\pi-server") == expected
    if os.name == "nt":
        with pytest.raises(ValueError, match="网络共享"):
            EasyTunnelApp._absolute_identity_path(r"\\server\share\pi-server")


class _FakePage:
    def __init__(self) -> None:
        self.opened: list[ft.Control] = []
        self.closed: list[ft.Control] = []
        self.clipboard = ""

    def open(self, control: ft.Control) -> None:
        self.opened.append(control)

    def close(self, control: ft.Control) -> None:
        self.closed.append(control)

    def set_clipboard(self, value: str) -> None:
        self.clipboard = value


def test_all_primary_views_construct_with_pinned_flet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]

    assert isinstance(app._build_sidebar(), ft.Container)
    assert app._tunnels_view() is not None
    assert app._logs_view() is not None
    assert app._settings_view() is not None

    app._open_form()
    assert page.opened
    assert isinstance(page.opened[-1], ft.AlertDialog)


def test_import_dialog_converts_variables_and_multiple_forwards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    key = tmp_path / "pi server"
    key.write_text("fake", encoding="utf-8")
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    app._open_import_dialog(None)
    assert app._import_command is not None
    app._import_command.value = f"""
PrivateKey={key}
MySqlPort=13306
RedisPort=16380

ssh -i $PrivateKey -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3
  -L 127.0.0.1:${{MySqlPort}}:127.0.0.1:3369
  -L 127.0.0.1:${{RedisPort}}:127.0.0.1:6380
  pi@pi.solitude.love -N -T
"""

    app._apply_import(None)

    imported = app._form_config()
    assert imported.identity_file == str(key.resolve())
    assert imported.keepalive_interval == 30
    assert [forward.name for forward in imported.forwards] == ["MySQL", "Redis"]
    assert [forward.local_port for forward in imported.forwards] == [13306, 16380]
    assert app._editing_id is None
    assert len(page.closed) == 1
    assert isinstance(page.opened[-1], ft.AlertDialog)


def test_tcp_service_action_uses_selected_forward(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    snapshot = app.manager.snapshots()[0]
    forward = LocalForward(
        name="Redis",
        bind_host="::1",
        local_port=16380,
        remote_host="127.0.0.1",
        remote_port=6380,
    )

    app._open_service(snapshot, forward)

    assert page.clipboard == "[::1]:16380"
