from __future__ import annotations

import asyncio
import ipaddress
import os
import subprocess
import threading
import webbrowser
from pathlib import Path

import flet as ft

from .config_store import ConfigError, ConfigStore
from .models import RuntimeSnapshot, TunnelConfig, TunnelState
from .ssh_manager import SSHManager


BG = "#F4F7FB"
SURFACE = "#FFFFFF"
SIDEBAR = "#101828"
TEXT = "#172033"
MUTED = "#667085"
PRIMARY = "#4F6BED"
PRIMARY_SOFT = "#EEF2FF"
GREEN = "#12A36D"
GREEN_SOFT = "#EAFBF4"
AMBER = "#E59A17"
RED = "#E5484D"
BORDER = "#E5EAF1"


def _app_data_path() -> Path:
    override = os.environ.get("EASYTUNNEL_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "EasyTunnel" / "tunnels.json"


def _project_sample_key() -> Path | None:
    candidate = Path(__file__).resolve().parents[2] / "pi-server"
    return candidate if candidate.is_file() else None


class EasyTunnelApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.store = ConfigStore(_app_data_path(), _project_sample_key())
        self.load_error = ""
        try:
            self.configs = self.store.load()
        except ConfigError as exc:
            self.configs = [self.store.example_tunnel()]
            self.load_error = str(exc)

        self.manager = SSHManager()
        self.manager.set_configs(self.configs)
        self.current_view = "tunnels"
        self.log_filter: str | None = None
        self.search_query = ""
        self.body = ft.Container(expand=True)
        self.nav_controls: dict[str, ft.Container] = {}
        self._last_fingerprint: tuple[object, ...] = ()
        self._form: dict[str, ft.Control] = {}
        self._form_dialog: ft.AlertDialog | None = None
        self._editing_id: str | None = None
        self.file_picker = ft.FilePicker(on_result=self._picked_key)
        self._toggle_lock = threading.Lock()
        self._toggle_targets: dict[str, bool] = {}
        self._toggle_workers: set[str] = set()

    def mount(self) -> None:
        page = self.page
        page.title = "EasyTunnel · SSH 隧道管理器"
        page.padding = 0
        page.spacing = 0
        page.bgcolor = BG
        page.theme_mode = ft.ThemeMode.LIGHT
        page.theme = ft.Theme(color_scheme_seed=PRIMARY, font_family="Segoe UI")
        page.window.width = 1240
        page.window.height = 790
        page.window.min_width = 960
        page.window.min_height = 680
        page.on_disconnect = self._on_disconnect
        page.overlay.append(self.file_picker)

        sidebar = self._build_sidebar()
        page.add(ft.Row([sidebar, self.body], expand=True, spacing=0))
        self._render()
        self._last_fingerprint = self._runtime_fingerprint()
        page.run_task(self._refresh_loop)

        if self.load_error:
            self._toast(self.load_error, error=True)
        for config in self.configs:
            if config.auto_connect:
                threading.Thread(target=self.manager.start, args=(config.id,), daemon=True).start()

    def _build_sidebar(self) -> ft.Container:
        brand = ft.Row(
            [
                ft.Container(
                    width=40,
                    height=40,
                    border_radius=12,
                    bgcolor=PRIMARY,
                    alignment=ft.alignment.center,
                    content=ft.Icon(ft.Icons.SWAP_HORIZ_ROUNDED, color="white", size=24),
                ),
                ft.Column(
                    [
                        ft.Text("EasyTunnel", color="white", size=18, weight=ft.FontWeight.BOLD),
                        ft.Text("安全地连接另一端", color="#98A2B3", size=11),
                    ],
                    spacing=1,
                ),
            ],
            spacing=12,
        )
        nav = ft.Column(spacing=7)
        for key, label, icon in (
            ("tunnels", "我的隧道", ft.Icons.HUB_OUTLINED),
            ("logs", "运行日志", ft.Icons.SUBJECT_ROUNDED),
            ("settings", "设置与帮助", ft.Icons.SETTINGS_OUTLINED),
        ):
            item = ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, size=20), ft.Text(label, size=14, weight=ft.FontWeight.BOLD)],
                    spacing=12,
                ),
                padding=ft.padding.symmetric(horizontal=15, vertical=12),
                border_radius=10,
                on_click=lambda _, view=key: self._change_view(view),
            )
            self.nav_controls[key] = item
            nav.controls.append(item)
        self._style_nav()

        footer = ft.Container(
            padding=14,
            border_radius=12,
            bgcolor="#1D2939",
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SHIELD_OUTLINED, color="#84ADFF", size=18),
                            ft.Text("安全默认值", color="white", size=13, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=8,
                    ),
                    ft.Text("私钥只保留路径，命令不会经过 Shell。", color="#98A2B3", size=11),
                ],
                spacing=7,
            ),
        )
        return ft.Container(
            width=232,
            bgcolor=SIDEBAR,
            padding=ft.padding.only(left=18, top=24, right=18, bottom=20),
            content=ft.Column(
                [brand, ft.Container(height=25), nav, ft.Container(expand=True), footer],
                expand=True,
            ),
        )

    def _style_nav(self) -> None:
        for key, item in self.nav_controls.items():
            selected = key == self.current_view
            item.bgcolor = "#263B70" if selected else None
            row = item.content
            if isinstance(row, ft.Row):
                for control in row.controls:
                    control.color = "white" if selected else "#98A2B3"

    def _change_view(self, view: str) -> None:
        self.current_view = view
        self._style_nav()
        self._render()

    def _render(self) -> None:
        if self.current_view == "tunnels":
            self.body.content = self._tunnels_view()
        elif self.current_view == "logs":
            self.body.content = self._logs_view()
        else:
            self.body.content = self._settings_view()
        self.page.update()

    def _tunnels_view(self) -> ft.Control:
        snapshots = self.manager.snapshots()
        connected = sum(item.state == TunnelState.CONNECTED for item in snapshots)
        connecting = sum(item.state == TunnelState.CONNECTING for item in snapshots)

        search = ft.TextField(
            value=self.search_query,
            hint_text="输入关键词并按回车搜索",
            prefix_icon=ft.Icons.SEARCH,
            height=44,
            width=310,
            border_color=BORDER,
            focused_border_color=PRIMARY,
            border_radius=12,
            content_padding=ft.padding.symmetric(horizontal=12),
            on_submit=self._search_changed,
        )
        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("我的隧道", size=27, color=TEXT, weight=ft.FontWeight.BOLD),
                        ft.Text("把 SSH 端口转发变成一个开关。", color=MUTED, size=13),
                    ],
                    spacing=3,
                ),
                ft.Row(
                    [
                        search,
                        ft.ElevatedButton(
                            "新建隧道",
                            icon=ft.Icons.ADD_ROUNDED,
                            bgcolor=PRIMARY,
                            color="white",
                            height=44,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=11)),
                            on_click=lambda _: self._open_form(),
                        ),
                    ],
                    spacing=12,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

        stats = ft.Row(
            [
                self._stat_card("已连接", str(connected), GREEN, GREEN_SOFT, ft.Icons.LINK_ROUNDED),
                self._stat_card("正在连接", str(connecting), AMBER, "#FFF7E8", ft.Icons.SYNC_ROUNDED),
                self._stat_card("全部隧道", str(len(snapshots)), PRIMARY, PRIMARY_SOFT, ft.Icons.HUB_OUTLINED),
            ],
            spacing=13,
        )

        query = self.search_query.strip().lower()
        filtered = [
            item
            for item in snapshots
            if not query
            or query in item.config.name.lower()
            or query in item.config.ssh_host.lower()
            or query in item.config.remote_host.lower()
        ]
        if filtered:
            cards: ft.Control = ft.Column([self._tunnel_card(item) for item in filtered], spacing=12)
        else:
            cards = ft.Container(
                height=260,
                alignment=ft.alignment.center,
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.ROUTE_OUTLINED, size=48, color="#B7C0CE"),
                        ft.Text("没有找到隧道", color=TEXT, size=16, weight=ft.FontWeight.BOLD),
                        ft.Text("清空搜索条件，或新建一条 SSH 隧道。", color=MUTED, size=12),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
            )
        return ft.Container(
            padding=ft.padding.only(left=30, top=25, right=30, bottom=30),
            content=ft.Column(
                [header, ft.Container(height=8), stats, ft.Container(height=4), cards],
                spacing=18,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        )

    @staticmethod
    def _stat_card(label: str, value: str, color: str, soft: str, icon: str) -> ft.Container:
        return ft.Container(
            expand=True,
            height=86,
            padding=16,
            border_radius=14,
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            content=ft.Row(
                [
                    ft.Container(
                        width=46,
                        height=46,
                        border_radius=12,
                        bgcolor=soft,
                        alignment=ft.alignment.center,
                        content=ft.Icon(icon, color=color, size=23),
                    ),
                    ft.Column(
                        [
                            ft.Text(value, color=TEXT, size=23, weight=ft.FontWeight.BOLD),
                            ft.Text(label, color=MUTED, size=12),
                        ],
                        spacing=0,
                    ),
                ],
                spacing=13,
            ),
        )

    def _tunnel_card(self, snapshot: RuntimeSnapshot) -> ft.Container:
        config = snapshot.config
        status_text, status_color, status_bg, status_icon = self._status_style(snapshot.state)
        busy = snapshot.state in {TunnelState.CONNECTING, TunnelState.STOPPING}
        service_icon = {
            "rdp": ft.Icons.DESKTOP_WINDOWS_OUTLINED,
            "web": ft.Icons.LANGUAGE_ROUNDED,
            "tcp": ft.Icons.CABLE_ROUNDED,
        }.get(config.service_type, ft.Icons.CABLE_ROUNDED)
        service_label = {"rdp": "远程桌面", "web": "Web 服务", "tcp": "TCP 服务"}.get(
            config.service_type, "TCP 服务"
        )
        subtitle = config.note or f"{config.username}@{config.ssh_host}"
        uptime = (
            f"开始于 {snapshot.started_at:%H:%M}"
            if snapshot.state == TunnelState.CONNECTED and snapshot.started_at
            else ""
        )

        status = ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=5),
            border_radius=20,
            bgcolor=status_bg,
            content=ft.Row(
                [ft.Icon(status_icon, color=status_color, size=14), ft.Text(status_text, color=status_color, size=11)],
                spacing=5,
                tight=True,
            ),
        )
        connection_line = ft.Row(
            [
                self._endpoint("本地入口", f"{config.bind_host}:{config.local_port}"),
                ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED, color="#98A2B3", size=18),
                self._endpoint("内网目标", f"{config.remote_host}:{config.remote_port}"),
                ft.Container(width=1, height=35, bgcolor=BORDER, margin=ft.margin.symmetric(horizontal=5)),
                self._endpoint("SSH 跳板", f"{config.username}@{config.ssh_host}:{config.ssh_port}"),
            ],
            spacing=13,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        error_line: ft.Control = ft.Container()
        if snapshot.last_error:
            error_line = ft.Container(
                margin=ft.margin.only(top=12),
                padding=ft.padding.symmetric(horizontal=11, vertical=8),
                border_radius=8,
                bgcolor="#FFF1F1",
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, color=RED, size=17),
                        ft.Text(snapshot.last_error, color="#B42318", size=11, expand=True),
                    ],
                    spacing=7,
                ),
            )

        switch = ft.Switch(
            value=snapshot.state in {TunnelState.CONNECTING, TunnelState.CONNECTED},
            disabled=busy,
            active_color=GREEN,
            on_change=lambda event, tunnel_id=config.id: self._toggle(tunnel_id, bool(event.control.value)),
        )
        open_button = ft.OutlinedButton(
            "打开服务",
            icon=ft.Icons.OPEN_IN_NEW_ROUNDED,
            height=37,
            disabled=snapshot.state != TunnelState.CONNECTED,
            style=ft.ButtonStyle(
                color=PRIMARY,
                side=ft.BorderSide(1, "#C7D2FE"),
                shape=ft.RoundedRectangleBorder(radius=9),
            ),
            on_click=lambda _, item=snapshot: self._open_service(item),
        )
        menu = ft.PopupMenuButton(
            icon=ft.Icons.MORE_HORIZ,
            items=[
                ft.PopupMenuItem(
                    text="编辑配置",
                    icon=ft.Icons.EDIT_OUTLINED,
                    on_click=lambda _, tunnel_id=config.id: self._edit(tunnel_id),
                ),
                ft.PopupMenuItem(
                    text="复制 SSH 命令",
                    icon=ft.Icons.CONTENT_COPY_OUTLINED,
                    on_click=lambda _, item=config: self._copy_command(item),
                ),
                ft.PopupMenuItem(
                    text="查看日志",
                    icon=ft.Icons.SUBJECT_ROUNDED,
                    on_click=lambda _, tunnel_id=config.id: self._show_logs(tunnel_id),
                ),
                ft.PopupMenuItem(
                    text="删除隧道",
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    on_click=lambda _, tunnel_id=config.id: self._confirm_delete(tunnel_id),
                ),
            ],
        )
        return ft.Container(
            padding=ft.padding.only(left=19, top=17, right=15, bottom=17),
            border_radius=14,
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=43,
                                height=43,
                                border_radius=11,
                                bgcolor=PRIMARY_SOFT,
                                alignment=ft.alignment.center,
                                content=ft.Icon(service_icon, color=PRIMARY, size=22),
                            ),
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                config.name,
                                                color=TEXT,
                                                size=16,
                                                weight=ft.FontWeight.BOLD,
                                                expand=True,
                                                no_wrap=True,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                            ),
                                            status,
                                            ft.Text(uptime, color=MUTED, size=11) if uptime else ft.Container(),
                                        ],
                                        spacing=9,
                                    ),
                                    ft.Text(f"{service_label}  ·  {subtitle}", color=MUTED, size=11),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            open_button,
                            switch,
                            menu,
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(height=1, bgcolor=BORDER, margin=ft.margin.symmetric(vertical=13)),
                    connection_line,
                    error_line,
                ],
                spacing=0,
            ),
        )

    @staticmethod
    def _endpoint(label: str, value: str) -> ft.Column:
        return ft.Column(
            [
                ft.Text(label, color="#98A2B3", size=10),
                ft.Text(
                    value,
                    color=TEXT,
                    size=12,
                    weight=ft.FontWeight.BOLD,
                    selectable=True,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
            spacing=3,
            expand=True,
        )

    @staticmethod
    def _status_style(state: TunnelState) -> tuple[str, str, str, str]:
        return {
            TunnelState.DISCONNECTED: ("未连接", MUTED, "#F2F4F7", ft.Icons.RADIO_BUTTON_UNCHECKED),
            TunnelState.CONNECTING: ("正在连接", AMBER, "#FFF7E8", ft.Icons.SYNC_ROUNDED),
            TunnelState.CONNECTED: ("运行中", GREEN, GREEN_SOFT, ft.Icons.CHECK_CIRCLE_OUTLINE),
            TunnelState.STOPPING: ("正在断开", AMBER, "#FFF7E8", ft.Icons.SYNC_ROUNDED),
            TunnelState.ERROR: ("连接失败", RED, "#FFF1F1", ft.Icons.ERROR_OUTLINE_ROUNDED),
        }[state]

    def _logs_view(self) -> ft.Control:
        snapshots = self.manager.snapshots()
        options = [ft.dropdown.Option("all", "全部隧道")]
        options.extend(ft.dropdown.Option(item.config.id, item.config.name) for item in snapshots)
        selected = self.log_filter if any(item.config.id == self.log_filter for item in snapshots) else "all"
        selector = ft.Dropdown(
            value=selected,
            options=options,
            width=210,
            border_color=BORDER,
            border_radius=10,
            on_change=self._log_filter_changed,
        )
        rows: list[ft.Control] = []
        selected_logs = [
            (entry, snapshot)
            for snapshot in snapshots
            if selected == "all" or snapshot.config.id == selected
            for entry in snapshot.logs
        ]
        selected_logs.sort(key=lambda item: item[0].timestamp)
        for entry, snapshot in selected_logs:
                color = {"error": RED, "success": GREEN}.get(entry.level, PRIMARY)
                icon = {"error": ft.Icons.ERROR_OUTLINE, "success": ft.Icons.CHECK_CIRCLE_OUTLINE}.get(
                    entry.level, ft.Icons.INFO_OUTLINE
                )
                rows.append(
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=14, vertical=11),
                        border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                        content=ft.Row(
                            [
                                ft.Text(entry.timestamp.strftime("%H:%M:%S"), width=70, color="#98A2B3", size=11),
                                ft.Icon(icon, color=color, size=17),
                                ft.Text(snapshot.config.name, width=150, color=TEXT, size=12, weight=ft.FontWeight.BOLD),
                                ft.Text(entry.message, color=MUTED, size=12, expand=True, selectable=True),
                            ],
                            spacing=10,
                        ),
                    )
                )
        if not rows:
            rows.append(
                ft.Container(
                    height=260,
                    alignment=ft.alignment.center,
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.RECEIPT_LONG_OUTLINED, size=44, color="#B7C0CE"),
                            ft.Text("还没有运行日志", color=TEXT, size=15, weight=ft.FontWeight.BOLD),
                            ft.Text("连接或断开隧道后，日志会显示在这里。", color=MUTED, size=12),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                )
            )
        return ft.Container(
            padding=ft.padding.only(left=30, top=25, right=30, bottom=30),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text("运行日志", size=27, color=TEXT, weight=ft.FontWeight.BOLD),
                                    ft.Text("OpenSSH 的状态与错误信息会保留在本次运行中。", color=MUTED, size=13),
                                ],
                                spacing=3,
                            ),
                            selector,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Container(
                        bgcolor=SURFACE,
                        border=ft.border.all(1, BORDER),
                        border_radius=14,
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                        content=ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO),
                        expand=True,
                    ),
                ],
                spacing=22,
                expand=True,
            ),
        )

    def _settings_view(self) -> ft.Control:
        ssh_path = self.manager.ssh_executable or "未找到"
        return ft.Container(
            padding=ft.padding.only(left=30, top=25, right=30, bottom=30),
            content=ft.Column(
                [
                    ft.Column(
                        [
                            ft.Text("设置与帮助", size=27, color=TEXT, weight=ft.FontWeight.BOLD),
                            ft.Text("运行环境与安全说明。", color=MUTED, size=13),
                        ],
                        spacing=3,
                    ),
                    self._settings_card(
                        "运行环境",
                        ft.Icons.TERMINAL_ROUNDED,
                        [
                            self._setting_row("OpenSSH 客户端", ssh_path, bool(self.manager.ssh_executable)),
                            self._setting_row("配置文件", str(self.store.path), True),
                            self._setting_row("配置数量", f"{len(self.configs)} 条隧道", True),
                        ],
                    ),
                    self._settings_card(
                        "连接安全",
                        ft.Icons.SECURITY_ROUNDED,
                        [
                            ft.Text("• 本地端口默认只绑定 127.0.0.1，不向局域网暴露。", color=MUTED, size=12),
                            ft.Text("• 仅保存私钥路径，不保存私钥内容、密码或口令。", color=MUTED, size=12),
                            ft.Text("• 首次连接默认接受新主机密钥；已有密钥变化时仍会拒绝连接。", color=MUTED, size=12),
                            ft.Text("• 加密私钥请预先加入 ssh-agent，本工具不会弹出密码输入框。", color=MUTED, size=12),
                        ],
                    ),
                    self._settings_card(
                        "命令示例",
                        ft.Icons.CODE_ROUNDED,
                        [
                            ft.Container(
                                padding=14,
                                border_radius=10,
                                bgcolor="#F8FAFC",
                                content=ft.Text(
                                    "ssh -i .\\pi-server -L 13389:192.168.3.88:3389 "
                                    "pi@pi.solitude.love -N",
                                    font_family="Consolas",
                                    size=12,
                                    color=TEXT,
                                    selectable=True,
                                ),
                            )
                        ],
                    ),
                ],
                spacing=18,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        )

    @staticmethod
    def _settings_card(title: str, icon: str, controls: list[ft.Control]) -> ft.Container:
        return ft.Container(
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            border_radius=14,
            padding=18,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, color=PRIMARY, size=20),
                            ft.Text(title, color=TEXT, size=15, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=9,
                    ),
                    ft.Divider(color=BORDER, height=18),
                    *controls,
                ],
                spacing=10,
            ),
        )

    @staticmethod
    def _setting_row(label: str, value: str, ok: bool) -> ft.Row:
        return ft.Row(
            [
                ft.Text(label, color=MUTED, size=12, width=150),
                ft.Text(value, color=TEXT if ok else RED, size=12, selectable=True, expand=True),
                ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.ERROR_OUTLINE, color=GREEN if ok else RED, size=17),
            ]
        )

    def _open_form(self, config: TunnelConfig | None = None) -> None:
        self._editing_id = config.id if config else None
        source = config or TunnelConfig(
            name="",
            note="",
            service_type="rdp",
            ssh_host="",
            username="",
            ssh_port=22,
            identity_file="",
            bind_host="127.0.0.1",
            local_port=13389,
            remote_host="",
            remote_port=3389,
        )

        def field(label: str, value: object, **kwargs: object) -> ft.TextField:
            return ft.TextField(
                label=label,
                value=str(value),
                border_color=BORDER,
                focused_border_color=PRIMARY,
                border_radius=10,
                text_size=13,
                label_style=ft.TextStyle(color=MUTED),
                on_change=self._update_preview,
                **kwargs,
            )

        self._form = {
            "name": field("隧道名称 *", source.name),
            "note": field("用途说明", source.note),
            "service_type": ft.Dropdown(
                label="服务类型",
                value=source.service_type,
                options=[
                    ft.dropdown.Option("rdp", "远程桌面 (RDP)"),
                    ft.dropdown.Option("web", "Web 服务"),
                    ft.dropdown.Option("tcp", "通用 TCP"),
                ],
                border_color=BORDER,
                focused_border_color=PRIMARY,
                border_radius=10,
                on_change=self._update_preview,
            ),
            "ssh_host": field("SSH 主机 *", source.ssh_host, hint_text="pi.solitude.love"),
            "username": field("用户名 *", source.username, hint_text="pi"),
            "ssh_port": field("SSH 端口", source.ssh_port, width=135, keyboard_type=ft.KeyboardType.NUMBER),
            "identity_file": field("私钥文件 *", source.identity_file, hint_text=r"E:\keys\id_ed25519"),
            "bind_host": field("本地绑定", source.bind_host, width=170),
            "local_port": field("本地端口 *", source.local_port, width=160, keyboard_type=ft.KeyboardType.NUMBER),
            "remote_host": field("内网目标主机 *", source.remote_host, hint_text="192.168.3.88"),
            "remote_port": field("目标端口 *", source.remote_port, width=160, keyboard_type=ft.KeyboardType.NUMBER),
            "strict_host_key": ft.Checkbox(label="严格校验主机密钥（主机必须已在 known_hosts 中）", value=source.strict_host_key),
            "auto_connect": ft.Checkbox(label="应用启动后自动连接", value=source.auto_connect),
        }
        self._form["error"] = ft.Text("", color=RED, size=11)
        self._form["preview"] = ft.Text("", color="#344054", size=11, font_family="Consolas", selectable=True)
        self._form["name"].expand = 2
        self._form["service_type"].expand = 1
        self._form["ssh_host"].expand = 2
        self._form["username"].expand = 1
        self._form["remote_host"].expand = True
        key_row = ft.Row(
            [
                self._form["identity_file"],
                ft.OutlinedButton("浏览", icon=ft.Icons.FOLDER_OPEN_OUTLINED, height=48, on_click=self._pick_key),
            ],
            spacing=10,
        )
        self._form["identity_file"].expand = True
        content = ft.Container(
            width=650,
            height=475,
            content=ft.Column(
                [
                    self._section_label("基本信息"),
                    ft.Row([self._form["name"], self._form["service_type"]], spacing=10),
                    self._form["note"],
                    self._section_label("SSH 连接"),
                    ft.Row(
                        [self._form["ssh_host"], self._form["username"], self._form["ssh_port"]],
                        spacing=10,
                    ),
                    key_row,
                    self._section_label("本地端口转发"),
                    ft.Row([self._form["bind_host"], self._form["local_port"]], spacing=10),
                    ft.Row([self._form["remote_host"], self._form["remote_port"]], spacing=10),
                    self._form["strict_host_key"],
                    self._form["auto_connect"],
                    self._section_label("命令预览"),
                    ft.Container(
                        bgcolor="#F8FAFC",
                        border=ft.border.all(1, BORDER),
                        border_radius=9,
                        padding=12,
                        content=self._form["preview"],
                    ),
                    self._form["error"],
                ],
                spacing=11,
                scroll=ft.ScrollMode.AUTO,
            ),
        )
        self._form_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑隧道" if config else "新建隧道", color=TEXT, weight=ft.FontWeight.BOLD),
            content=content,
            actions=[
                ft.TextButton("取消", on_click=lambda _: self._close_dialog()),
                ft.ElevatedButton(
                    "保存隧道",
                    icon=ft.Icons.SAVE_OUTLINED,
                    bgcolor=PRIMARY,
                    color="white",
                    on_click=self._save_form,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._update_preview(None)
        self.page.open(self._form_dialog)

    @staticmethod
    def _section_label(text: str) -> ft.Text:
        return ft.Text(text, size=12, color=PRIMARY, weight=ft.FontWeight.BOLD)

    def _form_config(self) -> TunnelConfig:
        get = lambda key: str(getattr(self._form[key], "value", "") or "").strip()
        identity_file = get("identity_file")
        if identity_file:
            identity_file = str(Path(identity_file).expanduser().resolve())
        return TunnelConfig(
            id=self._editing_id or TunnelConfig.__dataclass_fields__["id"].default_factory(),
            name=get("name"),
            note=get("note"),
            service_type=get("service_type"),
            ssh_host=get("ssh_host"),
            username=get("username"),
            ssh_port=int(get("ssh_port")),
            identity_file=identity_file,
            bind_host=get("bind_host"),
            local_port=int(get("local_port")),
            remote_host=get("remote_host"),
            remote_port=int(get("remote_port")),
            strict_host_key=bool(getattr(self._form["strict_host_key"], "value", False)),
            auto_connect=bool(getattr(self._form["auto_connect"], "value", False)),
        )

    def _update_preview(self, _: object) -> None:
        try:
            config = self._form_config()
            if config.validate(require_key_exists=False):
                raise ValueError("incomplete form")
            preview = self.manager.command_preview(config)
        except (ValueError, RuntimeError):
            preview = "请填写完整的连接参数后查看命令预览"
        control = self._form.get("preview")
        if isinstance(control, ft.Text):
            control.value = preview
            control.update() if control.page else None

    def _pick_key(self, _: object) -> None:
        try:
            self.file_picker.pick_files(
                dialog_title="选择 SSH 私钥",
                allow_multiple=False,
            )
        except Exception as exc:
            self._toast(f"无法打开文件选择器：{exc}", error=True)

    def _picked_key(self, event: object) -> None:
        files = getattr(event, "files", None)
        if not files:
            return
        control = self._form.get("identity_file")
        if isinstance(control, ft.TextField):
            control.value = files[0].path
            control.update()
        self._update_preview(None)

    def _save_form(self, _: object) -> None:
        error_control = self._form.get("error")
        try:
            config = self._form_config()
        except ValueError:
            self._set_form_error("端口必须填写为整数")
            return
        errors = config.validate(require_key_exists=True)
        if not self._is_loopback(config.bind_host):
            errors.append("为安全起见，本版本只允许绑定本机地址（例如 127.0.0.1 或 ::1）")
        for existing in self.configs:
            if existing.id != config.id and existing.bind_host == config.bind_host and existing.local_port == config.local_port:
                errors.append(f"本地端口与隧道“{existing.name}”重复")
                break
        if errors:
            self._set_form_error(errors[0])
            return

        new_configs = (
            [config if item.id == config.id else item for item in self.configs]
            if self._editing_id
            else [*self.configs, config]
        )
        try:
            self.store.save(new_configs)
        except ConfigError as exc:
            self._toast(str(exc), error=True)
            return
        self.configs = new_configs
        self.manager.set_configs(self.configs)
        if isinstance(error_control, ft.Text):
            error_control.value = ""
        self._close_dialog()
        self._last_fingerprint = ()
        self._render()
        self._toast("隧道配置已保存")

    def _set_form_error(self, message: str) -> None:
        control = self._form.get("error")
        if isinstance(control, ft.Text):
            control.value = message
            control.update()

    def _close_dialog(self) -> None:
        if self._form_dialog:
            self.page.close(self._form_dialog)

    def _toggle(self, tunnel_id: str, enabled: bool) -> None:
        with self._toggle_lock:
            self._toggle_targets[tunnel_id] = enabled
            if tunnel_id in self._toggle_workers:
                return
            self._toggle_workers.add(tunnel_id)
        threading.Thread(target=self._apply_toggle, args=(tunnel_id,), daemon=True).start()
        self._last_fingerprint = ()

    def _apply_toggle(self, tunnel_id: str) -> None:
        while True:
            with self._toggle_lock:
                target = self._toggle_targets.get(tunnel_id, False)
            if target:
                self.manager.start(tunnel_id)
            else:
                self.manager.stop(tunnel_id)
            with self._toggle_lock:
                if self._toggle_targets.get(tunnel_id, False) == target:
                    self._toggle_workers.discard(tunnel_id)
                    return

    def _edit(self, tunnel_id: str) -> None:
        snapshot = self.manager.snapshot(tunnel_id)
        if not snapshot:
            return
        if snapshot.state in {TunnelState.CONNECTING, TunnelState.CONNECTED, TunnelState.STOPPING}:
            self._toast("请先断开隧道，再编辑配置", error=True)
            return
        self._open_form(snapshot.config)

    def _copy_command(self, config: TunnelConfig) -> None:
        try:
            self.page.set_clipboard(self.manager.command_preview(config))
            self._toast("SSH 命令已复制")
        except Exception as exc:
            self._toast(f"复制失败：{exc}", error=True)

    def _show_logs(self, tunnel_id: str) -> None:
        self.log_filter = tunnel_id
        self._change_view("logs")

    def _confirm_delete(self, tunnel_id: str) -> None:
        snapshot = self.manager.snapshot(tunnel_id)
        if not snapshot:
            return
        if snapshot.state in {TunnelState.CONNECTING, TunnelState.CONNECTED, TunnelState.STOPPING}:
            self._toast("请先断开隧道，再删除配置", error=True)
            return
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("删除隧道？", weight=ft.FontWeight.BOLD),
            content=ft.Text(f"“{snapshot.config.name}”的配置将被删除，此操作不可撤销。"),
            actions=[
                ft.TextButton("取消", on_click=lambda _: self.page.close(dialog)),
                ft.ElevatedButton(
                    "删除",
                    bgcolor=RED,
                    color="white",
                    on_click=lambda _: self._delete(tunnel_id, dialog),
                ),
            ],
        )
        self.page.open(dialog)

    def _delete(self, tunnel_id: str, dialog: ft.AlertDialog) -> None:
        old = list(self.configs)
        self.configs = [item for item in self.configs if item.id != tunnel_id]
        self.manager.set_configs(self.configs)
        if not self._persist():
            self.configs = old
            self.manager.set_configs(old)
            return
        self.page.close(dialog)
        self._render()
        self._toast("隧道已删除")

    def _open_service(self, snapshot: RuntimeSnapshot) -> None:
        config = snapshot.config
        bind_host = config.bind_host.strip("[]")
        endpoint = f"[{bind_host}]:{config.local_port}" if ":" in bind_host else f"{bind_host}:{config.local_port}"
        try:
            if config.service_type == "rdp":
                if os.name != "nt":
                    raise RuntimeError("自动打开远程桌面目前仅支持 Windows")
                subprocess.Popen(["mstsc", f"/v:{endpoint}"], shell=False)
            elif config.service_type == "web":
                webbrowser.open(f"http://{endpoint}")
            else:
                self.page.set_clipboard(endpoint)
                self._toast("本地服务地址已复制")
        except (OSError, RuntimeError) as exc:
            self._toast(str(exc), error=True)

    def _search_changed(self, event: object) -> None:
        control = getattr(event, "control", None)
        self.search_query = str(getattr(control, "value", ""))
        self._render()

    def _log_filter_changed(self, event: object) -> None:
        value = str(getattr(getattr(event, "control", None), "value", "all"))
        self.log_filter = None if value == "all" else value
        self._render()

    def _persist(self) -> bool:
        try:
            self.store.save(self.configs)
            return True
        except ConfigError as exc:
            self._toast(str(exc), error=True)
            return False

    def _toast(self, message: str, *, error: bool = False) -> None:
        self.page.open(
            ft.SnackBar(
                content=ft.Text(message, color="white"),
                bgcolor=RED if error else "#344054",
                behavior=ft.SnackBarBehavior.FLOATING,
            )
        )

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            try:
                fingerprint = self._runtime_fingerprint()
                if fingerprint != self._last_fingerprint:
                    self._last_fingerprint = fingerprint
                    self._render()
            except Exception:
                return

    def _runtime_fingerprint(self) -> tuple[object, ...]:
        return tuple(
            (
                item.config.id,
                item.state.value,
                item.pid,
                item.last_error,
                len(item.logs),
            )
            for item in self.manager.snapshots()
        )

    @staticmethod
    def _is_loopback(host: str) -> bool:
        value = host.strip().strip("[]")
        if value.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(value).is_loopback
        except ValueError:
            return False

    def _on_disconnect(self, _: object) -> None:
        self.manager.shutdown()

def main(page: ft.Page) -> None:
    EasyTunnelApp(page).mount()
