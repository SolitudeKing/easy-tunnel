from pathlib import Path

import flet as ft
import pytest

from easytunnel.app import EasyTunnelApp


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


class _FakePage:
    def __init__(self) -> None:
        self.opened: list[ft.Control] = []

    def open(self, control: ft.Control) -> None:
        self.opened.append(control)


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
