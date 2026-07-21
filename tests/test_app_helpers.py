import asyncio
import os
from pathlib import Path

import flet as ft
import pytest
from packaging.version import Version

import easytunnel.app as app_module
from easytunnel.model.tunnel import LocalForward, TunnelConfig
from easytunnel.model.update import UpdateError, UpdateInfo
from easytunnel.view.app_view import EasyTunnelApp
from easytunnel.viewmodel.app_viewmodel import EasyTunnelViewModel


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
        self.overlay: list[ft.Control] = []
        self.controls: list[ft.Control] = []
        self.tasks: list[tuple[object, tuple[object, ...]]] = []
        self.window = _FakeWindow()

    def open(self, control: ft.Control) -> None:
        self.opened.append(control)

    def close(self, control: ft.Control) -> None:
        self.closed.append(control)

    def set_clipboard(self, value: str) -> None:
        self.clipboard = value

    def add(self, *controls: ft.Control) -> None:
        self.controls.extend(controls)

    def update(self) -> None:
        return None

    def run_task(self, handler: object, *args: object) -> None:
        self.tasks.append((handler, args))


class _FakeWindow:
    def __init__(self) -> None:
        self.width = 0
        self.height = 0
        self.min_width = 0
        self.min_height = 0
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _assert_control_tree_serializes(control: ft.Control) -> None:
    commands = control._build_add_commands()
    assert commands
    assert all(command.values and command.values[-1] for command in commands)


def _find_by_key(control: ft.Control, key: str) -> ft.Control:
    pending = [control]
    while pending:
        current = pending.pop()
        if getattr(current, "key", None) == key:
            return current
        pending.extend(current._get_children())
    raise AssertionError(f"control key not found: {key}")


def _multi_forward_config(tmp_path: Path) -> TunnelConfig:
    key = tmp_path / "id_ed25519"
    key.write_text("fake", encoding="utf-8")
    return TunnelConfig(
        id="tunnel-fixed-id",
        name="开发环境",
        note="多服务转发",
        ssh_host="pi.solitude.love",
        username="pi",
        ssh_port=2222,
        identity_file=str(key.resolve()),
        forwards=(
            LocalForward(
                id="forward-rdp",
                name="远程桌面",
                service_type="rdp",
                bind_host="127.0.0.1",
                local_port=13389,
                remote_host="192.168.3.88",
                remote_port=3389,
            ),
            LocalForward(
                id="forward-redis",
                name="Redis",
                service_type="tcp",
                bind_host="::1",
                local_port=16380,
                remote_host="::1",
                remote_port=6380,
            ),
            LocalForward(
                id="forward-mysql",
                name="MySQL",
                service_type="tcp",
                bind_host="127.0.0.1",
                local_port=13306,
                remote_host="127.0.0.1",
                remote_port=3369,
            ),
        ),
        strict_host_key=True,
        auto_connect=True,
        connect_timeout=17,
        keepalive_interval=41,
    )


def test_all_primary_views_construct_with_pinned_flet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]

    sidebar = app._build_sidebar()
    tunnels = app._tunnels_view()
    logs = app._logs_view()
    settings = app._settings_view()
    assert isinstance(sidebar, ft.Container)
    for control in (sidebar, tunnels, logs, settings):
        _assert_control_tree_serializes(control)

    app._open_form()
    assert page.opened
    assert isinstance(page.opened[-1], ft.AlertDialog)
    _assert_control_tree_serializes(page.opened[-1])


def test_mount_applies_mist_theme_and_serializable_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    page = _FakePage()
    app = EasyTunnelApp(
        page,  # type: ignore[arg-type]
        EasyTunnelViewModel(packaged_detector=lambda: False),
    )

    app.mount()

    assert page.bgcolor == app_module.BG
    assert page.theme_mode == ft.ThemeMode.LIGHT
    assert page.theme.color_scheme.primary == app_module.PRIMARY
    assert page.theme.color_scheme.surface == app_module.SURFACE
    assert isinstance(app.body.gradient, ft.LinearGradient)
    assert app.body.gradient.colors == [
        app_module.BG,
        app_module.SURFACE,
        app_module.BG_SECONDARY,
    ]
    assert len(app.body.gradient.stops) == len(app.body.gradient.colors)
    assert page.window.min_width == 960
    assert page.window.min_height == 680
    assert page.window.icon == app_module.APP_WINDOW_ICON_ASSET
    repo_root = Path(__file__).parents[1]
    window_icon = repo_root / "assets" / app_module.APP_WINDOW_ICON_ASSET
    assert window_icon.is_file()
    assert (
        window_icon.read_bytes()
        == (repo_root / "installer" / "EasyTunnel.ico").read_bytes()
    )
    assert len(page.controls) == 1
    shell = ft.Container(theme=page.theme, content=page.controls[0])
    _assert_control_tree_serializes(shell)


def test_tunnel_empty_states_remain_actionable_and_serializable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    config = _multi_forward_config(tmp_path)
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    app.configs = [config]
    app.manager.set_configs(app.configs)
    app.search_query = "not-a-match"

    filtered_view = app._tunnels_view()
    filtered_empty = _find_by_key(filtered_view, "tunnel-empty-state")
    assert isinstance(filtered_empty, ft.Container)
    _assert_control_tree_serializes(filtered_view)

    app.configs = []
    app.manager.set_configs([])
    app.search_query = ""
    fresh_view = app._tunnels_view()
    fresh_empty = _find_by_key(fresh_view, "tunnel-empty-state")
    assert isinstance(fresh_empty, ft.Container)
    _assert_control_tree_serializes(fresh_view)


def test_application_shell_uses_one_mist_sea_salt_semantic_system(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]

    assert app_module.FORM_BG == app_module.BG
    assert app_module.FORM_SURFACE == app_module.SURFACE
    assert app_module.FORM_ACCENT == app_module.PRIMARY
    assert app_module.FORM_BORDER == app_module.BORDER

    sidebar = app._build_sidebar()
    assert isinstance(sidebar.gradient, ft.LinearGradient)
    logo = _find_by_key(sidebar, "app-logo")
    assert isinstance(logo, ft.Image)
    assert logo.src == app_module.APP_LOGO_ASSET
    assert (Path(__file__).parents[1] / "assets" / logo.src).is_file()
    selected_nav = app.nav_controls["tunnels"]
    assert selected_nav.bgcolor == app_module.PRIMARY_SOFT
    assert selected_nav.border.left.width == 3
    assert selected_nav.border.left.color == app_module.PRIMARY

    tunnels = app._tunnels_view()
    summary = _find_by_key(tunnels, "tunnel-summary")
    assert isinstance(summary, ft.Container)
    assert isinstance(summary.gradient, ft.LinearGradient)
    assert isinstance(summary.content, ft.Row)

    logs = _find_by_key(app._logs_view(), "logs-shared-surface")
    settings = _find_by_key(app._settings_view(), "settings-main-surface")
    update_focus = _find_by_key(app._settings_view(), "settings-update-focus")
    assert isinstance(logs, ft.Container)
    assert isinstance(settings, ft.Container)
    assert isinstance(update_focus, ft.Container)
    assert isinstance(update_focus.gradient, ft.LinearGradient)

    primary = app._primary_button_style()
    secondary = app._secondary_button_style()
    danger = app._danger_button_style()
    assert primary.bgcolor[ft.ControlState.HOVERED] == app_module.PRIMARY_HOVER
    assert primary.bgcolor[ft.ControlState.PRESSED] == app_module.PRIMARY_ACTIVE
    assert primary.side[ft.ControlState.FOCUSED].width == 2
    assert secondary.side[ft.ControlState.FOCUSED].width == 2
    assert danger.side[ft.ControlState.FOCUSED].width == 2


def test_feedback_surfaces_serialize_with_mist_sea_salt_styles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    config = _multi_forward_config(tmp_path)
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    app.configs = [config]
    app.manager.set_configs(app.configs)

    app._confirm_delete(config.id)
    delete_dialog = page.opened[-1]
    assert isinstance(delete_dialog, ft.AlertDialog)
    assert delete_dialog.bgcolor == app_module.SURFACE
    assert isinstance(delete_dialog.shape, ft.RoundedRectangleBorder)
    assert delete_dialog.shape.radius == 24
    _assert_control_tree_serializes(delete_dialog)

    app._toast("连接已建立")
    snackbar = page.opened[-1]
    assert isinstance(snackbar, ft.SnackBar)
    assert snackbar.bgcolor == app_module.PRIMARY_ACTIVE
    assert snackbar.show_close_icon is True
    _assert_control_tree_serializes(snackbar)


def test_tunnel_form_uses_mist_sea_salt_visual_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]

    app._open_form()

    dialog = app._form_dialog
    assert dialog is not None
    assert dialog.bgcolor == app_module.FORM_SURFACE
    assert isinstance(dialog.shape, ft.RoundedRectangleBorder)
    assert dialog.shape.radius == 24
    assert isinstance(dialog.title, ft.Row)
    assert isinstance(dialog.content, ft.Container)
    assert dialog.content.width == 860
    assert dialog.content.height == 460
    assert isinstance(dialog.content.gradient, ft.LinearGradient)
    assert isinstance(dialog.actions[0], ft.OutlinedButton)
    assert isinstance(dialog.actions[1], ft.ElevatedButton)

    name_field = app._form["name"]
    assert isinstance(name_field, ft.TextField)
    assert name_field.filled is True
    assert name_field.fill_color == app_module.FORM_SURFACE
    assert name_field.border_color == app_module.FORM_BORDER_STRONG
    assert name_field.focused_border_color == app_module.FORM_ACCENT
    assert app._form_forward_rows[0].container.bgcolor == app_module.FORM_CARD


def test_edit_form_round_trips_multiple_forward_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    config = _multi_forward_config(tmp_path)
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]

    app._open_form(config)

    assert app._form_config() == config
    assert [row.title.value for row in app._form_forward_rows] == [
        "主转发",
        "附加转发 1",
        "附加转发 2",
    ]
    assert [row.delete_button.visible for row in app._form_forward_rows] == [
        False,
        True,
        True,
    ]


def test_dynamic_forward_rows_preserve_ids_and_preview_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    config = _multi_forward_config(tmp_path)
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    app.manager.ssh_executable = "ssh"
    app._open_form(config)

    app._remove_forward_form_row("forward-rdp")
    assert [row.forward_id for row in app._form_forward_rows] == [
        "forward-rdp",
        "forward-redis",
        "forward-mysql",
    ]

    app._remove_forward_form_row("forward-redis")
    app._add_forward_form_row()
    added = app._form_forward_rows[-1]
    added.name.value = "MinIO 控制台"
    added.service_type.value = "web"
    added.bind_host.value = "127.0.0.1"
    added.local_port.value = "19001"
    added.remote_host.value = "127.0.0.1"
    added.remote_port.value = "9001"

    rebuilt = app._form_config()
    rebuilt_ids = [forward.id for forward in rebuilt.forwards]
    assert rebuilt_ids[:2] == ["forward-rdp", "forward-mysql"]
    assert rebuilt.forwards[1] == config.forwards[2]
    assert rebuilt_ids[2] not in {
        "forward-rdp",
        "forward-redis",
        "forward-mysql",
    }

    app._update_preview(None)
    preview_control = app._form["preview"]
    assert isinstance(preview_control, ft.Text)
    preview = str(preview_control.value)
    specs = [forward.to_ssh_spec() for forward in rebuilt.forwards]
    assert all(spec in preview for spec in specs)
    assert [preview.index(spec) for spec in specs] == sorted(
        preview.index(spec) for spec in specs
    )

    added.local_port.value = "not-a-port"
    with pytest.raises(ValueError, match="第 3 条转发的本地端口"):
        app._form_config()
    app._update_preview(None)
    assert preview_control.value == "请填写完整的连接参数后查看命令预览"


def test_stale_form_generation_cannot_open_picker_for_reopened_form(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EASYTUNNEL_CONFIG", str(tmp_path / "tunnels.json"))
    page = _FakePage()
    app = EasyTunnelApp(page)  # type: ignore[arg-type]
    app._open_form()
    stale_generation = app._form_generation
    app._open_form()
    picker_calls: list[bool] = []
    monkeypatch.setattr(
        app.file_picker,
        "pick_files",
        lambda **_: picker_calls.append(True),
    )

    app._pick_key(None, generation=stale_generation)

    assert picker_calls == []
    assert app._file_picker_generation is None

    app._pick_key(None, generation=app._form_generation)

    assert picker_calls == [True]
    assert app._file_picker_generation == app._form_generation


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
    assert isinstance(page.opened[-1], ft.AlertDialog)
    _assert_control_tree_serializes(page.opened[-1])
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
    assert [forward.service_type for forward in imported.forwards] == ["tcp", "tcp"]
    assert [forward.remote_port for forward in imported.forwards] == [3369, 6380]
    assert len(app._form_forward_rows) == 2
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

    def fail_update_check(_: str) -> None:
        raise failure

    page = _FakePage()
    app = EasyTunnelApp(
        page,  # type: ignore[arg-type]
        EasyTunnelViewModel(
            packaged_detector=lambda: True,
            update_fetcher=fail_update_check,
        ),
    )
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
    page = _FakePage()
    app = EasyTunnelApp(
        page,  # type: ignore[arg-type]
        EasyTunnelViewModel(
            packaged_detector=lambda: True,
            update_fetcher=lambda _: None,
        ),
    )
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
    update = UpdateInfo(
        version=Version("0.2.0"),
        installer_name="EasyTunnel-Setup-0.2.0.exe",
        installer_url="https://example.test/EasyTunnel-Setup.exe",
        sha256="a" * 64,
        installer_size=3,
        release_url="https://example.test/release",
        release_notes="更新说明",
    )
    page = _FakePage()
    app = EasyTunnelApp(
        page,  # type: ignore[arg-type]
        EasyTunnelViewModel(
            packaged_detector=lambda: True,
            update_fetcher=lambda _: update,
        ),
    )
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
    _assert_control_tree_serializes(page.opened[-1])
    assert rendered_states == [True, False]
