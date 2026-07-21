import asyncio
import os
from pathlib import Path

import flet as ft
import pytest
from packaging.version import Version

import easytunnel.app as app_module
from easytunnel.app import EasyTunnelApp
from easytunnel.models import LocalForward
from easytunnel.updater import UpdateError, UpdateInfo


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


@pytest.mark.parametrize(
    "failure",
    [
        UpdateError("网络暂时不可用"),
        RuntimeError("unexpected failure"),
    ],
)
def test_update_check_failure_restores_manual_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    monkeypatch.setattr(app_module, "is_packaged_windows_app", lambda: True)

    def fail_update_check(_: str) -> None:
        raise failure

    monkeypatch.setattr(app_module, "fetch_latest_update", fail_update_check)
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    app.current_view = "settings"
    rendered_states: list[bool] = []
    monkeypatch.setattr(
        app,
        "_render",
        lambda: rendered_states.append(app._checking_update),
    )

    asyncio.run(app._check_for_update(manual=True))

    assert app._checking_update is False
    assert rendered_states == [True, False]
    assert "检查更新失败" in app._update_status
    assert page.opened


def test_update_check_reports_current_version_and_restores_button(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    monkeypatch.setattr(app_module, "is_packaged_windows_app", lambda: True)
    monkeypatch.setattr(app_module, "fetch_latest_update", lambda _: None)
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    app.current_view = "settings"
    rendered_states: list[bool] = []
    monkeypatch.setattr(
        app,
        "_render",
        lambda: rendered_states.append(app._checking_update),
    )

    asyncio.run(app._check_for_update())

    assert app._update_status == "当前已是最新稳定版本。"
    assert rendered_states == [True, False]


def test_update_check_opens_new_version_dialog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    monkeypatch.setattr(app_module, "is_packaged_windows_app", lambda: True)
    update = UpdateInfo(
        version=Version("0.2.0"),
        installer_name="EasyTunnel-Setup-0.2.0.exe",
        installer_url="https://example.test/EasyTunnel-Setup.exe",
        sha256="a" * 64,
        installer_size=3,
        release_url="https://example.test/release",
        release_notes="更新说明",
    )
    monkeypatch.setattr(app_module, "fetch_latest_update", lambda _: update)
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    app.current_view = "settings"
    rendered_states: list[bool] = []
    monkeypatch.setattr(
        app,
        "_render",
        lambda: rendered_states.append(app._checking_update),
    )

    asyncio.run(app._check_for_update())

    assert app._update_status == "发现新版本 0.2.0。"
    assert isinstance(page.opened[-1], ft.AlertDialog)
    assert rendered_states == [True, False]
