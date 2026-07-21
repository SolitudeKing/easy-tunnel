from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import flet as ft

from .. import __version__
from ..component.dialog.styles import dialog_surface_style
from ..component.dialog.tunnel_form import ForwardFormRow as _ForwardFormRow
from ..component.widget.theme import (
    AMBER,
    AMBER_SOFT,
    BG,
    BG_SECONDARY,
    BORDER,
    BORDER_STRONG,
    FORM_ACCENT,
    FORM_ACCENT_ACTIVE,
    FORM_ACCENT_LIGHT,
    FORM_ACCENT_SOFT,
    FORM_BG,
    FORM_BG_SECONDARY,
    FORM_BORDER,
    FORM_BORDER_STRONG,
    FORM_CARD,
    FORM_DANGER,
    FORM_DANGER_SOFT,
    FORM_HOVER,
    FORM_INSET,
    FORM_MUTED,
    FORM_SUCCESS,
    FORM_SURFACE,
    FORM_TEXT,
    FORM_TEXT_SECONDARY,
    GREEN,
    GREEN_SOFT,
    INSET,
    MUTED,
    PRIMARY,
    PRIMARY_ACTIVE,
    PRIMARY_LIGHT,
    PRIMARY_SOFT,
    RED,
    RED_ACTIVE,
    RED_SOFT,
    SIDEBAR,
    SURFACE,
    SURFACE_MUTED,
    TEXT,
    TEXT_SECONDARY,
    build_theme,
    danger_button_style,
    panel_shadow,
    primary_button_style,
    secondary_button_style,
)
from ..config.paths import (
    APP_LOGO_ASSET,
    APP_WINDOW_ICON_ASSET,
)
from ..model.runtime import RuntimeSnapshot
from ..model.tunnel import LocalForward, TunnelConfig, TunnelState
from ..model.update import UpdateInfo
from ..viewmodel.app_viewmodel import EasyTunnelViewModel, ViewModelError


class EasyTunnelApp:
    def __init__(
        self,
        page: ft.Page,
        view_model: EasyTunnelViewModel | None = None,
    ) -> None:
        self.page = page
        self.view_model = (
            view_model if view_model is not None else EasyTunnelViewModel()
        )
        self.body = ft.Container(expand=True)
        self.nav_controls: dict[str, ft.Container] = {}
        self._form: dict[str, ft.Control] = {}
        self._form_dialog: ft.AlertDialog | None = None
        self._import_dialog: ft.AlertDialog | None = None
        self._import_command: ft.TextField | None = None
        self._import_variables: ft.TextField | None = None
        self._import_error: ft.Text | None = None
        self._editing_id: str | None = None
        self._form_forward_rows: list[_ForwardFormRow] = []
        self._form_forwards_column: ft.Column | None = None
        self._form_generation = 0
        self._file_picker_generation: int | None = None
        self.file_picker = ft.FilePicker(on_result=self._picked_key)

    @property
    def store(self):
        return self.view_model.repository

    @property
    def manager(self):
        return self.view_model.tunnel_service

    @property
    def configs(self) -> list[TunnelConfig]:
        return self.view_model.configs

    @configs.setter
    def configs(self, value: list[TunnelConfig]) -> None:
        self.view_model.configs = value

    @property
    def load_error(self) -> str:
        return self.view_model.load_error

    @property
    def current_view(self) -> str:
        return self.view_model.current_view

    @current_view.setter
    def current_view(self, value: str) -> None:
        self.view_model.current_view = value

    @property
    def log_filter(self) -> str | None:
        return self.view_model.log_filter

    @log_filter.setter
    def log_filter(self, value: str | None) -> None:
        self.view_model.log_filter = value

    @property
    def search_query(self) -> str:
        return self.view_model.search_query

    @search_query.setter
    def search_query(self, value: str) -> None:
        self.view_model.search_query = value

    @property
    def _last_fingerprint(self) -> tuple[object, ...]:
        return self.view_model.last_runtime_fingerprint

    @_last_fingerprint.setter
    def _last_fingerprint(self, value: tuple[object, ...]) -> None:
        self.view_model.last_runtime_fingerprint = value

    @property
    def _available_update(self) -> UpdateInfo | None:
        return self.view_model.available_update

    @_available_update.setter
    def _available_update(self, value: UpdateInfo | None) -> None:
        self.view_model.available_update = value

    @property
    def _checking_update(self) -> bool:
        return self.view_model.checking_update

    @_checking_update.setter
    def _checking_update(self, value: bool) -> None:
        self.view_model.checking_update = value

    @property
    def _update_status(self) -> str:
        return self.view_model.update_status

    @_update_status.setter
    def _update_status(self, value: str) -> None:
        self.view_model.update_status = value

    def mount(self) -> None:
        page = self.page
        page.title = "EasyTunnel · SSH 隧道管理器"
        page.padding = 0
        page.spacing = 0
        page.bgcolor = BG
        page.theme_mode = ft.ThemeMode.LIGHT
        page.theme = build_theme()
        page.window.width = 1240
        page.window.height = 790
        page.window.min_width = 960
        page.window.min_height = 680
        page.window.icon = APP_WINDOW_ICON_ASSET
        page.on_disconnect = self._on_disconnect
        page.overlay.append(self.file_picker)

        self.body.gradient = ft.LinearGradient(
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right,
            colors=[BG, SURFACE, BG_SECONDARY],
            stops=[0, 0.58, 1],
        )
        sidebar = self._build_sidebar()
        page.add(ft.Row([sidebar, self.body], expand=True, spacing=0))
        self._render()
        self._last_fingerprint = self._runtime_fingerprint()
        page.run_task(self._refresh_loop)
        if self.view_model.is_packaged_app():
            page.run_task(self._check_for_update)

        if self.load_error:
            self._toast(self.load_error, error=True)
        self.view_model.start_auto_connect()

    def _build_sidebar(self) -> ft.Container:
        brand = ft.Row(
            [
                ft.Container(
                    width=44,
                    height=44,
                    border_radius=14,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    border=ft.border.all(1, SURFACE),
                    shadow=ft.BoxShadow(
                        blur_radius=18,
                        color=ft.Colors.with_opacity(0.16, PRIMARY),
                        offset=ft.Offset(0, 6),
                    ),
                    content=ft.Image(
                        key="app-logo",
                        src=APP_LOGO_ASSET,
                        width=44,
                        height=44,
                        fit=ft.ImageFit.COVER,
                        border_radius=14,
                        anti_alias=True,
                        semantics_label="EasyTunnel 应用图标",
                        error_content=ft.Container(
                            bgcolor=PRIMARY,
                            alignment=ft.alignment.center,
                            content=ft.Icon(
                                ft.Icons.SWAP_HORIZ_ROUNDED,
                                color=SURFACE,
                                size=24,
                            ),
                        ),
                    ),
                ),
                ft.Column(
                    [
                        ft.Text(
                            "EasyTunnel", color=TEXT, size=18, weight=ft.FontWeight.BOLD
                        ),
                        ft.Text("让连接保持清晰与安静", color=MUTED, size=12),
                    ],
                    spacing=1,
                ),
            ],
            spacing=12,
        )
        nav = ft.Column(spacing=8)
        for key, label, icon in (
            ("tunnels", "我的隧道", ft.Icons.HUB_OUTLINED),
            ("logs", "运行日志", ft.Icons.SUBJECT_ROUNDED),
            ("settings", "设置与帮助", ft.Icons.SETTINGS_OUTLINED),
        ):
            item = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, size=20),
                        ft.Text(label, size=14, weight=ft.FontWeight.BOLD),
                    ],
                    spacing=12,
                ),
                height=48,
                padding=ft.padding.symmetric(horizontal=14),
                border_radius=12,
                ink=True,
                ink_color=ft.Colors.with_opacity(0.08, PRIMARY),
                on_click=lambda _, view=key: self._change_view(view),
            )
            self.nav_controls[key] = item
            nav.controls.append(item)
        self._style_nav()

        footer = ft.Container(
            padding=ft.padding.only(top=16),
            border=ft.border.only(top=ft.BorderSide(1, BORDER)),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=32,
                                height=32,
                                border_radius=10,
                                bgcolor=PRIMARY_SOFT,
                                alignment=ft.alignment.center,
                                content=ft.Icon(
                                    ft.Icons.SHIELD_OUTLINED, color=PRIMARY, size=18
                                ),
                            ),
                            ft.Column(
                                [
                                    ft.Text(
                                        "本机安全模式",
                                        color=TEXT,
                                        size=12,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        f"EasyTunnel {__version__}",
                                        color=MUTED,
                                        size=12,
                                    ),
                                ],
                                spacing=1,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Text(
                        "私钥只保留路径，命令不会经过 Shell。", color=MUTED, size=12
                    ),
                ],
                spacing=10,
            ),
        )
        return ft.Container(
            width=244,
            bgcolor=SIDEBAR,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[SURFACE, SIDEBAR, PRIMARY_SOFT],
                stops=[0, 0.7, 1],
            ),
            border=ft.border.only(right=ft.BorderSide(1, BORDER)),
            padding=ft.padding.only(left=20, top=24, right=20, bottom=20),
            content=ft.Column(
                [
                    brand,
                    ft.Container(height=28),
                    ft.Text(
                        "工作区",
                        color=MUTED,
                        size=12,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Container(height=4),
                    nav,
                    ft.Container(expand=True),
                    footer,
                ],
                expand=True,
            ),
        )

    def _style_nav(self) -> None:
        for key, item in self.nav_controls.items():
            selected = key == self.current_view
            item.bgcolor = PRIMARY_SOFT if selected else None
            item.border = ft.border.only(
                left=ft.BorderSide(
                    3,
                    PRIMARY if selected else ft.Colors.TRANSPARENT,
                )
            )
            row = item.content
            if isinstance(row, ft.Row):
                for control in row.controls:
                    control.color = PRIMARY if selected else TEXT_SECONDARY

    @staticmethod
    def _panel_shadow() -> ft.BoxShadow:
        return panel_shadow()

    @staticmethod
    def _primary_button_style() -> ft.ButtonStyle:
        return primary_button_style()

    @staticmethod
    def _secondary_button_style() -> ft.ButtonStyle:
        return secondary_button_style()

    @staticmethod
    def _danger_button_style() -> ft.ButtonStyle:
        return danger_button_style()

    def _change_view(self, view: str) -> None:
        self.view_model.set_current_view(view)
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
        snapshots = self.view_model.snapshots()
        connected = sum(item.state == TunnelState.CONNECTED for item in snapshots)
        connecting = sum(item.state == TunnelState.CONNECTING for item in snapshots)

        search = ft.TextField(
            value=self.search_query,
            hint_text="输入关键词并按回车搜索",
            prefix_icon=ft.Icons.SEARCH,
            height=44,
            width=270,
            color=TEXT,
            cursor_color=PRIMARY,
            filled=True,
            fill_color=SURFACE,
            hover_color=BG_SECONDARY,
            border_color=BORDER_STRONG,
            focused_border_color=PRIMARY,
            focused_border_width=2,
            border_radius=12,
            content_padding=ft.padding.symmetric(horizontal=12),
            hint_style=ft.TextStyle(color=MUTED, size=12),
            on_submit=self._search_changed,
        )
        header = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            "我的隧道", size=27, color=TEXT, weight=ft.FontWeight.BOLD
                        ),
                        ft.Text("把 SSH 端口转发变成一个开关。", color=MUTED, size=13),
                    ],
                    spacing=3,
                ),
                ft.Row(
                    [
                        search,
                        ft.OutlinedButton(
                            "导入命令",
                            icon=ft.Icons.CONTENT_PASTE_GO_ROUNDED,
                            height=44,
                            style=self._secondary_button_style(),
                            on_click=self._open_import_dialog,
                        ),
                        ft.ElevatedButton(
                            "新建隧道",
                            icon=ft.Icons.ADD_ROUNDED,
                            height=44,
                            style=self._primary_button_style(),
                            on_click=lambda _: self._open_form(),
                        ),
                    ],
                    spacing=12,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            wrap=True,
            run_spacing=12,
        )

        stats = ft.Container(
            key="tunnel-summary",
            height=88,
            padding=ft.padding.symmetric(horizontal=8, vertical=6),
            border_radius=20,
            bgcolor=SURFACE_MUTED,
            gradient=ft.LinearGradient(
                begin=ft.alignment.center_left,
                end=ft.alignment.center_right,
                colors=[SURFACE, SURFACE_MUTED, BG_SECONDARY],
            ),
            border=ft.border.all(1, BORDER),
            shadow=self._panel_shadow(),
            content=ft.Row(
                [
                    self._stat_card(
                        "已连接",
                        str(connected),
                        GREEN,
                        GREEN_SOFT,
                        ft.Icons.LINK_ROUNDED,
                    ),
                    ft.Container(width=1, height=44, bgcolor=BORDER),
                    self._stat_card(
                        "正在连接",
                        str(connecting),
                        AMBER,
                        AMBER_SOFT,
                        ft.Icons.SYNC_ROUNDED,
                    ),
                    ft.Container(width=1, height=44, bgcolor=BORDER),
                    self._stat_card(
                        "全部隧道",
                        str(len(snapshots)),
                        PRIMARY,
                        PRIMARY_SOFT,
                        ft.Icons.HUB_OUTLINED,
                    ),
                ],
                spacing=0,
            ),
        )

        query = self.search_query.strip().lower()
        filtered = [
            item
            for item in snapshots
            if not query
            or query in item.config.name.lower()
            or query in item.config.ssh_host.lower()
            or any(
                query in forward.name.lower() or query in forward.remote_host.lower()
                for forward in item.config.forwards
            )
        ]
        if filtered:
            cards: ft.Control = ft.Column(
                [self._tunnel_card(item) for item in filtered], spacing=12
            )
        else:
            has_search = bool(query) and bool(snapshots)
            empty_action: ft.Control
            if has_search:
                empty_action = ft.OutlinedButton(
                    "清除搜索",
                    icon=ft.Icons.FILTER_ALT_OFF_ROUNDED,
                    height=44,
                    style=self._secondary_button_style(),
                    on_click=self._clear_search,
                )
            else:
                empty_action = ft.ElevatedButton(
                    "新建第一条隧道",
                    icon=ft.Icons.ADD_ROUNDED,
                    height=44,
                    style=self._primary_button_style(),
                    on_click=lambda _: self._open_form(),
                )
            cards = ft.Container(
                key="tunnel-empty-state",
                height=280,
                alignment=ft.alignment.center,
                border_radius=20,
                bgcolor=ft.Colors.with_opacity(0.56, SURFACE),
                border=ft.border.all(1, BORDER),
                content=ft.Column(
                    [
                        ft.Container(
                            width=64,
                            height=64,
                            border_radius=20,
                            bgcolor=PRIMARY_SOFT,
                            alignment=ft.alignment.center,
                            content=ft.Icon(
                                ft.Icons.ROUTE_OUTLINED,
                                size=32,
                                color=PRIMARY,
                            ),
                        ),
                        ft.Text(
                            "没有匹配的隧道" if has_search else "还没有隧道",
                            color=TEXT,
                            size=18,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            f"没有找到包含“{self.search_query.strip()}”的配置。"
                            if has_search
                            else "创建一条配置，把常用 SSH 转发变成一个开关。",
                            color=MUTED,
                            size=12,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=4),
                        empty_action,
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=10,
                ),
            )
        return ft.Container(
            padding=ft.padding.only(left=32, top=28, right=32, bottom=32),
            content=ft.Column(
                [header, ft.Container(height=4), stats, cards],
                spacing=20,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        )

    @staticmethod
    def _stat_card(
        label: str, value: str, color: str, soft: str, icon: str
    ) -> ft.Container:
        return ft.Container(
            expand=True,
            height=72,
            padding=ft.padding.symmetric(horizontal=16),
            content=ft.Row(
                [
                    ft.Container(
                        width=40,
                        height=40,
                        border_radius=12,
                        bgcolor=soft,
                        alignment=ft.alignment.center,
                        content=ft.Icon(icon, color=color, size=21),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                value, color=TEXT, size=22, weight=ft.FontWeight.BOLD
                            ),
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
        primary_forward = config.forwards[0]
        status_text, status_color, status_bg, status_icon = self._status_style(
            snapshot.state
        )
        busy = snapshot.state in {TunnelState.CONNECTING, TunnelState.STOPPING}
        service_icon = {
            "rdp": ft.Icons.DESKTOP_WINDOWS_OUTLINED,
            "web": ft.Icons.LANGUAGE_ROUNDED,
            "tcp": ft.Icons.CABLE_ROUNDED,
        }.get(primary_forward.service_type, ft.Icons.CABLE_ROUNDED)
        service_label = {"rdp": "远程桌面", "web": "Web 服务", "tcp": "TCP 服务"}.get(
            primary_forward.service_type, "TCP 服务"
        )
        if len(config.forwards) > 1:
            service_label = f"{len(config.forwards)} 条本地转发"
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
                [
                    ft.Icon(status_icon, color=status_color, size=14),
                    ft.Text(status_text, color=status_color, size=12),
                ],
                spacing=5,
                tight=True,
            ),
        )
        connection_lines = ft.Column(
            [
                self._forward_row(
                    snapshot,
                    forward,
                    show_ssh=index == 0,
                )
                for index, forward in enumerate(config.forwards)
            ],
            spacing=10,
        )
        error_line: ft.Control = ft.Container()
        if snapshot.last_error:
            error_line = ft.Container(
                margin=ft.margin.only(top=12),
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                border_radius=12,
                bgcolor=RED_SOFT,
                border=ft.border.all(1, ft.Colors.with_opacity(0.28, RED)),
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.ERROR_OUTLINE_ROUNDED, color=RED, size=17),
                        ft.Text(snapshot.last_error, color=RED, size=12, expand=True),
                    ],
                    spacing=7,
                ),
            )

        switch = ft.Switch(
            value=snapshot.state in {TunnelState.CONNECTING, TunnelState.CONNECTED},
            disabled=busy,
            active_color=GREEN,
            active_track_color=ft.Colors.with_opacity(0.34, GREEN),
            inactive_thumb_color=SURFACE,
            inactive_track_color=INSET,
            track_outline_color=BORDER_STRONG,
            tooltip=(
                f"断开 {config.name}"
                if snapshot.state in {TunnelState.CONNECTING, TunnelState.CONNECTED}
                else f"连接 {config.name}"
            ),
            on_change=lambda event, tunnel_id=config.id: self._toggle(
                tunnel_id, bool(event.control.value)
            ),
        )
        menu = ft.PopupMenuButton(
            icon=ft.Icons.MORE_HORIZ,
            icon_color=TEXT_SECONDARY,
            bgcolor=SURFACE,
            surface_tint_color=SURFACE,
            shadow_color=ft.Colors.with_opacity(0.18, PRIMARY_LIGHT),
            elevation=8,
            shape=ft.RoundedRectangleBorder(radius=12),
            tooltip=f"{config.name} 的更多操作",
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
                    on_click=lambda _, tunnel_id=config.id: self._confirm_delete(
                        tunnel_id
                    ),
                ),
            ],
        )
        return ft.Container(
            key=f"tunnel-card-{config.id}",
            padding=ft.padding.only(left=19, top=17, right=15, bottom=17),
            border_radius=20,
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            shadow=ft.BoxShadow(
                blur_radius=16,
                color=ft.Colors.with_opacity(0.06, PRIMARY_LIGHT),
                offset=ft.Offset(0, 4),
            ),
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
                                            ft.Text(uptime, color=MUTED, size=12)
                                            if uptime
                                            else ft.Container(),
                                        ],
                                        spacing=9,
                                    ),
                                    ft.Text(
                                        f"{service_label}  ·  {subtitle}",
                                        color=MUTED,
                                        size=12,
                                    ),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            switch,
                            menu,
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Container(
                        height=1,
                        bgcolor=BORDER,
                        margin=ft.margin.symmetric(vertical=13),
                    ),
                    connection_lines,
                    error_line,
                ],
                spacing=0,
            ),
        )

    def _forward_row(
        self,
        snapshot: RuntimeSnapshot,
        forward: LocalForward,
        *,
        show_ssh: bool,
    ) -> ft.Row:
        action_label = "复制地址" if forward.service_type == "tcp" else "打开服务"
        controls: list[ft.Control] = [
            self._endpoint(forward.name, self._forward_endpoint(forward)),
            ft.Icon(ft.Icons.ARROW_FORWARD_ROUNDED, color=MUTED, size=18),
            self._endpoint("内网目标", f"{forward.remote_host}:{forward.remote_port}"),
        ]
        if show_ssh:
            config = snapshot.config
            controls.extend(
                [
                    ft.Container(
                        width=1,
                        height=35,
                        bgcolor=BORDER,
                        margin=ft.margin.symmetric(horizontal=5),
                    ),
                    self._endpoint(
                        "SSH 跳板",
                        f"{config.username}@{config.ssh_host}:{config.ssh_port}",
                    ),
                ]
            )
        controls.append(
            ft.OutlinedButton(
                action_label,
                icon=ft.Icons.CONTENT_COPY_OUTLINED
                if forward.service_type == "tcp"
                else ft.Icons.OPEN_IN_NEW_ROUNDED,
                height=44,
                disabled=snapshot.state != TunnelState.CONNECTED,
                style=self._secondary_button_style(),
                on_click=lambda _, item=snapshot, rule=forward: self._open_service(
                    item, rule
                ),
            )
        )
        return ft.Row(
            controls,
            spacing=13,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    @staticmethod
    def _forward_endpoint(forward: LocalForward) -> str:
        return EasyTunnelViewModel.forward_endpoint(forward)

    @staticmethod
    def _endpoint(label: str, value: str) -> ft.Column:
        return ft.Column(
            [
                ft.Text(label, color=MUTED, size=12),
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
            TunnelState.DISCONNECTED: (
                "未连接",
                MUTED,
                INSET,
                ft.Icons.RADIO_BUTTON_UNCHECKED,
            ),
            TunnelState.CONNECTING: (
                "正在连接",
                AMBER,
                AMBER_SOFT,
                ft.Icons.SYNC_ROUNDED,
            ),
            TunnelState.CONNECTED: (
                "运行中",
                GREEN,
                GREEN_SOFT,
                ft.Icons.CHECK_CIRCLE_OUTLINE,
            ),
            TunnelState.STOPPING: (
                "正在断开",
                AMBER,
                AMBER_SOFT,
                ft.Icons.SYNC_ROUNDED,
            ),
            TunnelState.ERROR: (
                "连接失败",
                RED,
                RED_SOFT,
                ft.Icons.ERROR_OUTLINE_ROUNDED,
            ),
        }[state]

    def _logs_view(self) -> ft.Control:
        snapshots = self.view_model.snapshots()
        options = [ft.dropdown.Option("all", "全部隧道")]
        options.extend(
            ft.dropdown.Option(item.config.id, item.config.name) for item in snapshots
        )
        selected = (
            self.log_filter
            if any(item.config.id == self.log_filter for item in snapshots)
            else "all"
        )
        selector = ft.Dropdown(
            value=selected,
            options=options,
            label="筛选隧道",
            width=230,
            color=TEXT,
            filled=True,
            fill_color=SURFACE,
            hover_color=BG_SECONDARY,
            border_color=BORDER_STRONG,
            focused_border_color=PRIMARY,
            focused_border_width=2,
            border_radius=12,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=10),
            label_style=ft.TextStyle(color=MUTED, size=12),
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
            icon = {
                "error": ft.Icons.ERROR_OUTLINE,
                "success": ft.Icons.CHECK_CIRCLE_OUTLINE,
            }.get(entry.level, ft.Icons.INFO_OUTLINE)
            level_label = {"error": "错误", "success": "成功"}.get(entry.level, "信息")
            rows.append(
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=18, vertical=12),
                    border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                    content=ft.Row(
                        [
                            ft.Text(
                                entry.timestamp.strftime("%H:%M:%S"),
                                width=76,
                                color=MUTED,
                                size=12,
                                font_family="Consolas",
                            ),
                            ft.Row(
                                [
                                    ft.Icon(icon, color=color, size=17),
                                    ft.Text(
                                        level_label,
                                        color=color,
                                        size=12,
                                        weight=ft.FontWeight.W_600,
                                    ),
                                ],
                                width=76,
                                spacing=6,
                            ),
                            ft.Text(
                                snapshot.config.name,
                                width=150,
                                color=TEXT,
                                size=12,
                                weight=ft.FontWeight.BOLD,
                                no_wrap=True,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                entry.message,
                                color=TEXT_SECONDARY,
                                size=12,
                                expand=True,
                                selectable=True,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
                            ft.Container(
                                width=60,
                                height=60,
                                border_radius=20,
                                bgcolor=PRIMARY_SOFT,
                                alignment=ft.alignment.center,
                                content=ft.Icon(
                                    ft.Icons.RECEIPT_LONG_OUTLINED,
                                    size=30,
                                    color=PRIMARY,
                                ),
                            ),
                            ft.Text(
                                "还没有运行日志",
                                color=TEXT,
                                size=16,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "连接或断开隧道后，日志会显示在这里。",
                                color=MUTED,
                                size=12,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                )
            )
        log_table = ft.Container(
            key="logs-shared-surface",
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            border_radius=20,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=self._panel_shadow(),
            content=ft.Column(
                [
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=18, vertical=14),
                        border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                        content=ft.Row(
                            [
                                ft.Row(
                                    [
                                        ft.Container(
                                            width=36,
                                            height=36,
                                            border_radius=12,
                                            bgcolor=PRIMARY_SOFT,
                                            alignment=ft.alignment.center,
                                            content=ft.Icon(
                                                ft.Icons.STREAM_ROUNDED,
                                                color=PRIMARY,
                                                size=20,
                                            ),
                                        ),
                                        ft.Column(
                                            [
                                                ft.Text(
                                                    "事件流",
                                                    color=TEXT,
                                                    size=14,
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                                ft.Text(
                                                    f"当前显示 {len(selected_logs)} 条日志",
                                                    color=MUTED,
                                                    size=12,
                                                ),
                                            ],
                                            spacing=1,
                                        ),
                                    ],
                                    spacing=10,
                                ),
                                selector,
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                    ),
                    ft.Container(
                        bgcolor=SURFACE_MUTED,
                        padding=ft.padding.symmetric(horizontal=18, vertical=9),
                        border=ft.border.only(bottom=ft.BorderSide(1, BORDER)),
                        content=ft.Row(
                            [
                                ft.Text("时间", width=76, color=MUTED, size=12),
                                ft.Text("级别", width=76, color=MUTED, size=12),
                                ft.Text("隧道", width=150, color=MUTED, size=12),
                                ft.Text("详情", color=MUTED, size=12, expand=True),
                            ],
                            spacing=12,
                        ),
                    ),
                    ft.Column(rows, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True),
                ],
                spacing=0,
                expand=True,
            ),
            expand=True,
        )
        return ft.Container(
            padding=ft.padding.only(left=32, top=28, right=32, bottom=32),
            content=ft.Column(
                [
                    ft.Column(
                        [
                            ft.Text(
                                "运行日志",
                                size=27,
                                color=TEXT,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "OpenSSH 的状态与错误信息会保留在本次运行中。",
                                color=MUTED,
                                size=13,
                            ),
                        ],
                        spacing=3,
                    ),
                    log_table,
                ],
                spacing=22,
                expand=True,
            ),
        )

    def _settings_view(self) -> ft.Control:
        ssh_path = self.view_model.ssh_executable or "未找到"
        update_message = self._update_status or self._default_update_message()
        environment = ft.Container(
            key="settings-main-surface",
            expand=7,
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            border_radius=20,
            padding=20,
            shadow=self._panel_shadow(),
            content=ft.Column(
                [
                    self._settings_section_header(
                        "运行环境",
                        "应用正在使用的本机工具与配置。",
                        ft.Icons.TERMINAL_ROUNDED,
                    ),
                    ft.Container(height=2),
                    self._setting_row(
                        "OpenSSH 客户端",
                        ssh_path,
                        bool(self.view_model.ssh_executable),
                    ),
                    self._setting_row("配置文件", str(self.view_model.config_path)),
                    self._setting_row("配置数量", f"{len(self.configs)} 条隧道"),
                    ft.Divider(color=BORDER, height=28),
                    self._settings_section_header(
                        "连接安全",
                        "默认策略优先保护本机端口与身份信息。",
                        ft.Icons.SECURITY_ROUNDED,
                    ),
                    ft.Container(height=2),
                    self._safety_row("本地端口默认只绑定 127.0.0.1，不向局域网暴露。"),
                    self._safety_row("仅保存私钥路径，不保存私钥内容、密码或口令。"),
                    self._safety_row(
                        "首次连接接受新主机密钥；已有密钥变化时仍会拒绝连接。"
                    ),
                    self._safety_row(
                        "加密私钥请预先加入 ssh-agent，本工具不会弹出密码输入框。"
                    ),
                ],
                spacing=10,
            ),
        )
        update_panel = ft.Container(
            key="settings-update-focus",
            padding=20,
            border_radius=20,
            bgcolor=SURFACE,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[SURFACE, PRIMARY_SOFT],
            ),
            border=ft.border.all(1, BORDER),
            shadow=self._panel_shadow(),
            content=ft.Column(
                [
                    self._settings_section_header(
                        "软件更新",
                        "从 GitHub Release 获取稳定版本。",
                        ft.Icons.SYSTEM_UPDATE_ALT_ROUNDED,
                    ),
                    ft.Container(height=2),
                    ft.Row(
                        [
                            ft.Text("当前版本", color=MUTED, size=12),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=10, vertical=5),
                                border_radius=999,
                                bgcolor=SURFACE,
                                border=ft.border.all(1, BORDER),
                                content=ft.Text(
                                    f"v{__version__}",
                                    color=PRIMARY,
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(update_message, color=TEXT_SECONDARY, size=12),
                    ft.OutlinedButton(
                        "检查中…" if self._checking_update else "立即检查",
                        icon=ft.Icons.HOURGLASS_TOP_ROUNDED
                        if self._checking_update
                        else ft.Icons.REFRESH_ROUNDED,
                        width=132,
                        height=44,
                        disabled=self._checking_update,
                        style=self._secondary_button_style(),
                        on_click=lambda _: self._request_update_check(),
                    ),
                ],
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.START,
            ),
        )
        command_panel = ft.Container(
            padding=20,
            border_radius=20,
            bgcolor=SURFACE,
            border=ft.border.all(1, BORDER),
            content=ft.Column(
                [
                    self._settings_section_header(
                        "命令示例",
                        "与图形配置等价的安全 SSH 命令。",
                        ft.Icons.CODE_ROUNDED,
                    ),
                    ft.Container(
                        padding=16,
                        border_radius=12,
                        bgcolor=INSET,
                        border=ft.border.all(1, BORDER),
                        content=ft.Text(
                            "ssh -i .\\pi-server -o IdentitiesOnly=yes "
                            "-o ExitOnForwardFailure=yes -o ServerAliveInterval=30 "
                            "-o ServerAliveCountMax=3 "
                            "-L 127.0.0.1:13389:192.168.3.88:3389 "
                            "-N -T pi@pi.solitude.love",
                            font_family="Consolas",
                            size=12,
                            color=TEXT,
                            selectable=True,
                        ),
                    ),
                ],
                spacing=14,
            ),
        )
        return ft.Container(
            padding=ft.padding.only(left=32, top=28, right=32, bottom=32),
            content=ft.Column(
                [
                    ft.Column(
                        [
                            ft.Text(
                                "设置与帮助",
                                size=27,
                                color=TEXT,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text("运行环境与安全说明。", color=MUTED, size=13),
                        ],
                        spacing=3,
                    ),
                    ft.Row(
                        [
                            environment,
                            ft.Column(
                                [update_panel, command_panel],
                                spacing=16,
                                expand=5,
                            ),
                        ],
                        spacing=16,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                ],
                spacing=22,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
        )

    @staticmethod
    def _settings_section_header(title: str, description: str, icon: str) -> ft.Row:
        return ft.Row(
            [
                ft.Container(
                    width=40,
                    height=40,
                    border_radius=12,
                    bgcolor=PRIMARY_SOFT,
                    alignment=ft.alignment.center,
                    content=ft.Icon(icon, color=PRIMARY, size=20),
                ),
                ft.Column(
                    [
                        ft.Text(title, color=TEXT, size=15, weight=ft.FontWeight.BOLD),
                        ft.Text(description, color=MUTED, size=12),
                    ],
                    spacing=1,
                    expand=True,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    @staticmethod
    def _safety_row(message: str) -> ft.Row:
        return ft.Row(
            [
                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED, color=GREEN, size=18),
                ft.Text(message, color=TEXT_SECONDARY, size=12, expand=True),
            ],
            spacing=9,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    @staticmethod
    def _setting_row(label: str, value: str, status: bool | None = None) -> ft.Row:
        controls: list[ft.Control] = [
            ft.Text(label, color=MUTED, size=12, width=126),
            ft.Text(
                value,
                color=RED if status is False else TEXT,
                size=12,
                selectable=True,
                expand=True,
                no_wrap=True,
                overflow=ft.TextOverflow.ELLIPSIS,
                tooltip=value,
            ),
        ]
        if status is not None:
            controls.append(
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE if status else ft.Icons.ERROR_OUTLINE,
                    color=GREEN if status else RED,
                    size=17,
                )
            )
        return ft.Row(
            controls,
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _open_import_dialog(self, _: object) -> None:
        self._import_command = ft.TextField(
            label="SSH 命令",
            hint_text=(
                "ssh -i $PrivateKey -L 127.0.0.1:${LocalPort}:127.0.0.1:3306 "
                "user@gateway -N -T"
            ),
            multiline=True,
            min_lines=7,
            max_lines=12,
            color=TEXT,
            cursor_color=PRIMARY,
            selection_color=ft.Colors.with_opacity(0.24, PRIMARY),
            filled=True,
            fill_color=SURFACE,
            hover_color=BG_SECONDARY,
            border_color=BORDER_STRONG,
            border_width=1,
            focused_border_color=PRIMARY,
            focused_border_width=2,
            border_radius=12,
            text_size=12,
            text_style=ft.TextStyle(font_family="Consolas"),
            label_style=ft.TextStyle(color=MUTED, size=12, weight=ft.FontWeight.W_600),
            hint_style=ft.TextStyle(color=MUTED, size=12, font_family="Consolas"),
        )
        self._import_variables = ft.TextField(
            label="变量定义（可选，每行 NAME=value）",
            hint_text="PrivateKey=E:\\keys\\pi-server\nLocalPort=13306",
            multiline=True,
            min_lines=3,
            max_lines=6,
            color=TEXT,
            cursor_color=PRIMARY,
            selection_color=ft.Colors.with_opacity(0.24, PRIMARY),
            filled=True,
            fill_color=SURFACE,
            hover_color=BG_SECONDARY,
            border_color=BORDER_STRONG,
            border_width=1,
            focused_border_color=PRIMARY,
            focused_border_width=2,
            border_radius=12,
            text_size=12,
            text_style=ft.TextStyle(font_family="Consolas"),
            label_style=ft.TextStyle(color=MUTED, size=12, weight=ft.FontWeight.W_600),
            hint_style=ft.TextStyle(color=MUTED, size=12, font_family="Consolas"),
        )
        self._import_error = ft.Text("", color=RED, size=12)
        self._import_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Container(
                        width=48,
                        height=48,
                        border_radius=12,
                        alignment=ft.alignment.center,
                        gradient=ft.LinearGradient(
                            begin=ft.alignment.top_left,
                            end=ft.alignment.bottom_right,
                            colors=[PRIMARY_ACTIVE, PRIMARY, PRIMARY_LIGHT],
                        ),
                        shadow=ft.BoxShadow(
                            blur_radius=18,
                            color=ft.Colors.with_opacity(0.24, PRIMARY),
                            offset=ft.Offset(0, 6),
                        ),
                        content=ft.Icon(
                            ft.Icons.CONTENT_PASTE_GO_ROUNDED,
                            color=SURFACE,
                            size=24,
                        ),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "安全导入 SSH 命令",
                                color=TEXT,
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "将现有命令解析为可检查的隧道配置",
                                color=MUTED,
                                size=12,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        border_radius=999,
                        bgcolor=PRIMARY_SOFT,
                        border=ft.border.all(1, BORDER),
                        content=ft.Text(
                            "仅解析，不执行",
                            color=PRIMARY,
                            size=12,
                            weight=ft.FontWeight.W_600,
                        ),
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                width=720,
                height=440,
                padding=20,
                bgcolor=BG,
                gradient=ft.LinearGradient(
                    begin=ft.alignment.top_left,
                    end=ft.alignment.bottom_right,
                    colors=[SURFACE, BG, BG_SECONDARY],
                ),
                border=ft.border.all(1, BORDER),
                content=ft.Column(
                    [
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=14, vertical=11),
                            border_radius=12,
                            bgcolor=PRIMARY_SOFT,
                            border=ft.border.all(1, BORDER),
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.SHIELD_OUTLINED, color=PRIMARY, size=19
                                    ),
                                    ft.Text(
                                        "只解析 -i、-p、-L、-N、-T 和允许的安全选项；"
                                        "不会执行粘贴内容。",
                                        color=TEXT_SECONDARY,
                                        size=12,
                                        expand=True,
                                    ),
                                ],
                                spacing=9,
                            ),
                        ),
                        self._import_command,
                        self._import_variables,
                        ft.Text(
                            "也可把 NAME=value 行放在 SSH 命令前。普通 PowerShell 局部变量不会自动继承；"
                            f"相对私钥路径按 {Path.cwd()} 解析。",
                            color=MUTED,
                            size=12,
                        ),
                        self._import_error,
                    ],
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ),
            **dialog_surface_style(
                "安全导入 SSH 命令",
                content_padding=0,
                actions_top=14,
            ),
            actions=[
                ft.OutlinedButton(
                    "取消",
                    height=44,
                    style=self._secondary_button_style(),
                    on_click=lambda _: self.page.close(self._import_dialog),
                ),
                ft.ElevatedButton(
                    "解析到表单",
                    icon=ft.Icons.INPUT_ROUNDED,
                    height=44,
                    style=self._primary_button_style(),
                    on_click=self._apply_import,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(self._import_dialog)

    def _apply_import(self, _: object) -> None:
        command_text = (
            str(self._import_command.value or "") if self._import_command else ""
        )
        variable_text = (
            str(self._import_variables.value or "") if self._import_variables else ""
        )
        try:
            config = self.view_model.import_ssh_command(command_text, variable_text)
        except ValueError as exc:
            self._set_import_error(str(exc))
            return
        if self._import_dialog:
            self.page.close(self._import_dialog)
        self._open_form(config, as_new=True)

    def _set_import_error(self, message: str) -> None:
        if self._import_error:
            self._import_error.value = message
            self._import_error.update() if self._import_error.page else None

    @staticmethod
    def _split_import_content(text: str) -> tuple[str, tuple[str, ...]]:
        return EasyTunnelViewModel.split_import_content(text)

    @staticmethod
    def _suggest_forward(remote_port: int, index: int) -> tuple[str, str]:
        return EasyTunnelViewModel.suggest_forward(remote_port, index)

    @staticmethod
    def _absolute_identity_path(value: str) -> str:
        return EasyTunnelViewModel.absolute_identity_path(value)

    def _form_field(
        self,
        label: str,
        value: object,
        **kwargs: object,
    ) -> ft.TextField:
        return ft.TextField(
            label=label,
            value=str(value),
            height=52,
            color=FORM_TEXT,
            cursor_color=FORM_ACCENT,
            selection_color=ft.Colors.with_opacity(0.24, FORM_ACCENT),
            filled=True,
            fill_color=FORM_SURFACE,
            hover_color=FORM_BG_SECONDARY,
            border_color=FORM_BORDER_STRONG,
            border_width=1,
            focused_border_color=FORM_ACCENT,
            focused_border_width=2,
            border_radius=12,
            text_size=14,
            label_style=ft.TextStyle(
                color=FORM_MUTED,
                size=12,
                weight=ft.FontWeight.W_600,
            ),
            hint_style=ft.TextStyle(color=FORM_MUTED, size=12),
            on_change=self._update_preview,
            **kwargs,
        )

    def _form_dropdown(
        self,
        label: str,
        value: str,
        options: list[ft.dropdown.Option],
    ) -> ft.Dropdown:
        return ft.Dropdown(
            label=label,
            value=value,
            options=options,
            color=FORM_TEXT,
            text_size=14,
            filled=True,
            fill_color=FORM_SURFACE,
            hover_color=FORM_BG_SECONDARY,
            border_color=FORM_BORDER_STRONG,
            border_width=1,
            focused_border_color=FORM_ACCENT,
            focused_border_width=2,
            border_radius=12,
            content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
            label_style=ft.TextStyle(
                color=FORM_MUTED,
                size=12,
                weight=ft.FontWeight.W_600,
            ),
            on_change=self._update_preview,
        )

    @staticmethod
    def _form_primary_button_style() -> ft.ButtonStyle:
        return EasyTunnelApp._primary_button_style()

    @staticmethod
    def _form_secondary_button_style() -> ft.ButtonStyle:
        return EasyTunnelApp._secondary_button_style()

    @staticmethod
    def _form_section_header(
        title: str,
        description: str,
        icon: str,
    ) -> ft.Row:
        return ft.Row(
            [
                ft.Container(
                    width=36,
                    height=36,
                    border_radius=12,
                    bgcolor=FORM_ACCENT_SOFT,
                    alignment=ft.alignment.center,
                    content=ft.Icon(icon, color=FORM_ACCENT, size=20),
                ),
                ft.Column(
                    [
                        ft.Text(
                            title,
                            size=14,
                            color=FORM_TEXT,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(description, size=12, color=FORM_MUTED),
                    ],
                    spacing=1,
                    expand=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _build_forward_form_row(
        self,
        forward: LocalForward | None,
        *,
        generation: int,
    ) -> _ForwardFormRow:
        forward_id = forward.id if forward else uuid4().hex
        name = self._form_field("服务名称 *", forward.name if forward else "")
        service_type = self._form_dropdown(
            "服务类型",
            forward.service_type if forward else "tcp",
            [
                ft.dropdown.Option("rdp", "远程桌面 (RDP)"),
                ft.dropdown.Option("web", "Web 服务"),
                ft.dropdown.Option("tcp", "通用 TCP"),
            ],
        )
        bind_host = self._form_field(
            "本地绑定 *",
            forward.bind_host if forward else "127.0.0.1",
        )
        local_port = self._form_field(
            "本地端口 *",
            forward.local_port if forward else "",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        remote_host = self._form_field(
            "目标主机 *",
            forward.remote_host if forward else "127.0.0.1",
            hint_text="192.168.3.88 或 127.0.0.1",
        )
        remote_port = self._form_field(
            "目标端口 *",
            forward.remote_port if forward else "",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        name.expand = 2
        service_type.expand = 1
        bind_host.expand = 2
        local_port.expand = 1
        remote_host.expand = 2
        remote_port.expand = 1

        title = ft.Text("", color=FORM_TEXT, size=14, weight=ft.FontWeight.BOLD)
        delete_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
            icon_color=FORM_DANGER,
            bgcolor=FORM_DANGER_SOFT,
            hover_color=ft.Colors.with_opacity(0.14, FORM_DANGER),
            focus_color=ft.Colors.with_opacity(0.18, FORM_DANGER),
            width=44,
            height=44,
            tooltip="删除这条附加转发",
            on_click=lambda _, row_id=forward_id, form_generation=generation: (
                self._remove_forward_form_row(
                    row_id,
                    generation=form_generation,
                )
            ),
        )
        container = ft.Container(
            bgcolor=FORM_CARD,
            border=ft.border.all(1, FORM_BORDER),
            border_radius=20,
            padding=16,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=32,
                                height=32,
                                border_radius=8,
                                bgcolor=FORM_SURFACE,
                                border=ft.border.all(1, FORM_BORDER),
                                alignment=ft.alignment.center,
                                content=ft.Icon(
                                    ft.Icons.ROUTE_ROUNDED,
                                    color=FORM_ACCENT,
                                    size=18,
                                ),
                            ),
                            title,
                            ft.Text(
                                "本地入口 → 目标服务",
                                color=FORM_MUTED,
                                size=12,
                            ),
                            ft.Container(expand=True),
                            delete_button,
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row([name, service_type], spacing=12),
                    ft.Row([bind_host, local_port], spacing=12),
                    ft.Row([remote_host, remote_port], spacing=12),
                ],
                spacing=12,
            ),
        )
        return _ForwardFormRow(
            forward_id=forward_id,
            name=name,
            service_type=service_type,
            bind_host=bind_host,
            local_port=local_port,
            remote_host=remote_host,
            remote_port=remote_port,
            title=title,
            delete_button=delete_button,
            container=container,
        )

    def _refresh_forward_form_rows(self) -> None:
        for index, row in enumerate(self._form_forward_rows):
            row.title.value = "主转发" if index == 0 else f"附加转发 {index}"
            row.delete_button.visible = index > 0
        if self._form_forwards_column is None:
            return
        self._form_forwards_column.controls = [
            row.container for row in self._form_forward_rows
        ]
        if self._form_forwards_column.page:
            self._form_forwards_column.update()

    def _add_forward_form_row(
        self,
        _: object = None,
        *,
        generation: int | None = None,
    ) -> None:
        if generation is not None and generation != self._form_generation:
            return
        row = self._build_forward_form_row(
            None,
            generation=self._form_generation,
        )
        self._form_forward_rows.append(row)
        self._refresh_forward_form_rows()
        self._update_preview(None)

    def _remove_forward_form_row(
        self,
        row_id: str,
        *,
        generation: int | None = None,
    ) -> None:
        if generation is not None and generation != self._form_generation:
            return
        index = next(
            (
                item_index
                for item_index, row in enumerate(self._form_forward_rows)
                if row.forward_id == row_id
            ),
            -1,
        )
        if index <= 0:
            return
        self._form_forward_rows.pop(index)
        self._refresh_forward_form_rows()
        self._update_preview(None)

    def _open_form(
        self, config: TunnelConfig | None = None, *, as_new: bool = False
    ) -> None:
        self._form_generation += 1
        generation = self._form_generation
        self._editing_id = config.id if config and not as_new else None
        source = config or TunnelConfig(
            name="",
            note="",
            ssh_host="",
            username="",
            ssh_port=22,
            identity_file="",
            forwards=(
                LocalForward(
                    name="主服务",
                    service_type="rdp",
                    bind_host="127.0.0.1",
                    local_port=13389,
                    remote_host="",
                    remote_port=3389,
                ),
            ),
        )

        self._form = {
            "name": self._form_field("隧道名称 *", source.name),
            "note": self._form_field("用途说明", source.note),
            "ssh_host": self._form_field(
                "SSH 主机 *",
                source.ssh_host,
                hint_text="pi.solitude.love",
            ),
            "username": self._form_field("用户名 *", source.username, hint_text="pi"),
            "ssh_port": self._form_field(
                "SSH 端口",
                source.ssh_port,
                width=135,
                keyboard_type=ft.KeyboardType.NUMBER,
            ),
            "identity_file": self._form_field(
                "私钥文件 *",
                source.identity_file,
                hint_text=r"E:\keys\id_ed25519",
            ),
            "connect_timeout": self._form_field(
                "连接超时（秒）",
                source.connect_timeout,
                keyboard_type=ft.KeyboardType.NUMBER,
            ),
            "keepalive_interval": self._form_field(
                "保活间隔（秒）",
                source.keepalive_interval,
                keyboard_type=ft.KeyboardType.NUMBER,
            ),
            "strict_host_key": ft.Checkbox(
                label="严格校验主机密钥（主机必须已在 known_hosts 中）",
                value=source.strict_host_key,
                active_color=FORM_ACCENT,
                check_color=FORM_SURFACE,
                hover_color=FORM_HOVER,
                focus_color=ft.Colors.with_opacity(0.24, FORM_ACCENT),
                border_side=ft.BorderSide(width=1, color=FORM_BORDER_STRONG),
                label_style=ft.TextStyle(color=FORM_TEXT_SECONDARY, size=12),
                on_change=self._update_preview,
            ),
            "auto_connect": ft.Checkbox(
                label="应用启动后自动连接",
                value=source.auto_connect,
                active_color=FORM_ACCENT,
                check_color=FORM_SURFACE,
                hover_color=FORM_HOVER,
                focus_color=ft.Colors.with_opacity(0.24, FORM_ACCENT),
                border_side=ft.BorderSide(width=1, color=FORM_BORDER_STRONG),
                label_style=ft.TextStyle(color=FORM_TEXT_SECONDARY, size=12),
            ),
        }
        self._form["error"] = ft.Text(
            "",
            color=FORM_DANGER,
            size=12,
            weight=ft.FontWeight.W_600,
        )
        self._form["preview"] = ft.Text(
            "",
            color=FORM_TEXT_SECONDARY,
            size=12,
            font_family="Consolas",
            selectable=True,
        )
        self._form["name"].expand = 2
        self._form["ssh_host"].expand = 2
        self._form["username"].expand = 1
        self._form_forward_rows = [
            self._build_forward_form_row(forward, generation=generation)
            for forward in source.forwards
        ]
        self._form_forwards_column = ft.Column(spacing=12)
        self._refresh_forward_form_rows()
        key_row = ft.Row(
            [
                self._form["identity_file"],
                ft.OutlinedButton(
                    "浏览",
                    icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                    height=52,
                    style=self._form_secondary_button_style(),
                    on_click=lambda event, form_generation=generation: self._pick_key(
                        event,
                        generation=form_generation,
                    ),
                ),
            ],
            spacing=12,
        )
        self._form["identity_file"].expand = True
        self._form["connect_timeout"].expand = 1
        self._form["keepalive_interval"].expand = 1

        forward_section_header = self._form_section_header(
            "本地端口转发",
            "一条 SSH 会话可以承载多条本地入口",
            ft.Icons.ROUTE_ROUNDED,
        )
        forward_section_header.expand = True
        add_forward_button = ft.OutlinedButton(
            "添加转发",
            icon=ft.Icons.ADD_LINK_ROUNDED,
            height=44,
            style=self._form_secondary_button_style(),
            on_click=lambda event, form_generation=generation: (
                self._add_forward_form_row(
                    event,
                    generation=form_generation,
                )
            ),
        )
        security_items = [
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE_OUTLINE_ROUNDED,
                        color=FORM_SUCCESS,
                        size=16,
                    ),
                    ft.Text(text, color=FORM_TEXT_SECONDARY, size=12),
                ],
                spacing=8,
            )
            for text in (
                "仅使用指定私钥身份",
                "任一转发失败立即退出",
                "禁用交互会话与 TTY",
            )
        ]
        content = ft.Container(
            width=860,
            height=460,
            padding=20,
            gradient=ft.LinearGradient(
                colors=[FORM_BG, FORM_BG_SECONDARY],
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
            ),
            theme=ft.Theme(
                color_scheme_seed=FORM_ACCENT,
                font_family="Segoe UI",
            ),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            self._form_section_header(
                                "基本信息",
                                "用清晰的名称标识这组连接",
                                ft.Icons.TUNE_ROUNDED,
                            ),
                            self._form["name"],
                            self._form["note"],
                            ft.Divider(
                                height=1,
                                thickness=1,
                                color=FORM_BORDER,
                            ),
                            self._form_section_header(
                                "SSH 连接",
                                "填写跳板机、账号与私钥位置",
                                ft.Icons.KEY_ROUNDED,
                            ),
                            ft.Row(
                                [
                                    self._form["ssh_host"],
                                    self._form["username"],
                                    self._form["ssh_port"],
                                ],
                                spacing=12,
                            ),
                            key_row,
                            ft.Divider(
                                height=1,
                                thickness=1,
                                color=FORM_BORDER,
                            ),
                            ft.Row(
                                [forward_section_header, add_forward_button],
                                spacing=12,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            self._form_forwards_column,
                        ],
                        spacing=16,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                    ft.Container(
                        width=1,
                        height=420,
                        margin=ft.margin.symmetric(horizontal=4),
                        bgcolor=FORM_BORDER,
                    ),
                    ft.Container(
                        width=300,
                        padding=ft.padding.only(left=12),
                        content=ft.Column(
                            [
                                self._form_section_header(
                                    "连接保护",
                                    "稳定且可预期的 SSH 会话策略",
                                    ft.Icons.SHIELD_OUTLINED,
                                ),
                                ft.Row(
                                    [
                                        self._form["connect_timeout"],
                                        self._form["keepalive_interval"],
                                    ],
                                    spacing=12,
                                ),
                                ft.Container(
                                    bgcolor=FORM_ACCENT_SOFT,
                                    border=ft.border.all(1, FORM_BORDER),
                                    border_radius=12,
                                    padding=16,
                                    content=ft.Column(
                                        [
                                            ft.Text(
                                                "安全默认值",
                                                color=FORM_ACCENT_ACTIVE,
                                                size=12,
                                                weight=ft.FontWeight.BOLD,
                                            ),
                                            *security_items,
                                        ],
                                        spacing=8,
                                    ),
                                ),
                                self._form["strict_host_key"],
                                self._form["auto_connect"],
                                ft.Divider(
                                    height=1,
                                    thickness=1,
                                    color=FORM_BORDER,
                                ),
                                self._form_section_header(
                                    "命令预览",
                                    "参数会随表单内容实时更新",
                                    ft.Icons.TERMINAL_ROUNDED,
                                ),
                                ft.Container(
                                    height=126,
                                    bgcolor=FORM_INSET,
                                    border=ft.border.all(1, FORM_BORDER),
                                    border_radius=12,
                                    padding=16,
                                    content=ft.Column(
                                        [self._form["preview"]],
                                        scroll=ft.ScrollMode.AUTO,
                                    ),
                                ),
                                self._form["error"],
                            ],
                            spacing=12,
                            scroll=ft.ScrollMode.AUTO,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        ),
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        )
        dialog_title = ft.Row(
            [
                ft.Container(
                    width=48,
                    height=48,
                    border_radius=12,
                    alignment=ft.alignment.center,
                    gradient=ft.LinearGradient(
                        colors=[
                            FORM_ACCENT_ACTIVE,
                            FORM_ACCENT,
                            FORM_ACCENT_LIGHT,
                        ],
                        begin=ft.alignment.top_left,
                        end=ft.alignment.bottom_right,
                    ),
                    shadow=ft.BoxShadow(
                        blur_radius=18,
                        color=ft.Colors.with_opacity(0.24, FORM_ACCENT),
                        offset=ft.Offset(0, 6),
                    ),
                    content=ft.Icon(
                        ft.Icons.HUB_OUTLINED,
                        color=FORM_SURFACE,
                        size=24,
                    ),
                ),
                ft.Column(
                    [
                        ft.Text(
                            "编辑隧道" if self._editing_id else "新建隧道",
                            color=FORM_TEXT,
                            size=20,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            "配置 SSH 入口、本地转发与连接保护",
                            color=FORM_MUTED,
                            size=12,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=10, vertical=6),
                    border_radius=999,
                    bgcolor=FORM_ACCENT_SOFT,
                    border=ft.border.all(1, FORM_BORDER),
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.WAVES_ROUNDED,
                                color=FORM_ACCENT,
                                size=16,
                            ),
                            ft.Text(
                                "雾境海盐",
                                color=FORM_ACCENT_ACTIVE,
                                size=12,
                                weight=ft.FontWeight.W_600,
                            ),
                        ],
                        spacing=6,
                    ),
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._form_dialog = ft.AlertDialog(
            modal=True,
            title=dialog_title,
            content=content,
            **dialog_surface_style(
                "SSH 隧道配置",
                content_padding=0,
                actions_top=14,
            ),
            actions=[
                ft.OutlinedButton(
                    "取消",
                    height=44,
                    style=self._form_secondary_button_style(),
                    on_click=lambda _, form_generation=generation: self._close_dialog(
                        generation=form_generation
                    ),
                ),
                ft.ElevatedButton(
                    "保存隧道",
                    icon=ft.Icons.SAVE_OUTLINED,
                    height=44,
                    style=self._form_primary_button_style(),
                    on_click=lambda event, form_generation=generation: self._save_form(
                        event,
                        generation=form_generation,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._update_preview(None)
        self.page.open(self._form_dialog)

    def _form_config(self) -> TunnelConfig:
        def get(key: str) -> str:
            return str(getattr(self._form[key], "value", "") or "").strip()

        def integer(key: str, label: str) -> int:
            try:
                return int(get(key))
            except ValueError as exc:
                raise ValueError(f"{label}必须填写为整数") from exc

        def row_value(control: ft.Control) -> str:
            return str(getattr(control, "value", "") or "").strip()

        def row_integer(
            control: ft.Control,
            *,
            row_number: int,
            label: str,
        ) -> int:
            try:
                return int(row_value(control))
            except ValueError as exc:
                raise ValueError(
                    f"第 {row_number} 条转发的{label}必须填写为整数"
                ) from exc

        identity_file = get("identity_file")
        if identity_file:
            identity_file = self._absolute_identity_path(identity_file)
        forwards = tuple(
            LocalForward(
                id=row.forward_id,
                name=row_value(row.name),
                service_type=row_value(row.service_type),
                bind_host=row_value(row.bind_host),
                local_port=row_integer(
                    row.local_port,
                    row_number=index,
                    label="本地端口",
                ),
                remote_host=row_value(row.remote_host),
                remote_port=row_integer(
                    row.remote_port,
                    row_number=index,
                    label="目标端口",
                ),
            )
            for index, row in enumerate(self._form_forward_rows, start=1)
        )
        return TunnelConfig(
            id=self._editing_id or uuid4().hex,
            name=get("name"),
            note=get("note"),
            ssh_host=get("ssh_host"),
            username=get("username"),
            ssh_port=integer("ssh_port", "SSH 端口"),
            identity_file=identity_file,
            forwards=forwards,
            strict_host_key=bool(
                getattr(self._form["strict_host_key"], "value", False)
            ),
            auto_connect=bool(getattr(self._form["auto_connect"], "value", False)),
            connect_timeout=integer("connect_timeout", "连接超时"),
            keepalive_interval=integer("keepalive_interval", "保活间隔"),
        )

    def _update_preview(self, _: object) -> None:
        try:
            config = self._form_config()
            if config.validate(require_key_exists=False):
                raise ValueError("incomplete form")
            preview = self.view_model.command_preview(config)
        except (ValueError, RuntimeError):
            preview = "请填写完整的连接参数后查看命令预览"
        control = self._form.get("preview")
        if isinstance(control, ft.Text):
            control.value = preview
            control.update() if control.page else None

    def _pick_key(
        self,
        _: object,
        *,
        generation: int | None = None,
    ) -> None:
        if generation is not None and generation != self._form_generation:
            return
        try:
            self._file_picker_generation = (
                generation if generation is not None else self._form_generation
            )
            self.file_picker.pick_files(
                dialog_title="选择 SSH 私钥",
                allow_multiple=False,
            )
        except Exception as exc:
            self._toast(f"无法打开文件选择器：{exc}", error=True)

    def _picked_key(self, event: object) -> None:
        files = getattr(event, "files", None)
        if (
            not files
            or self._file_picker_generation != self._form_generation
            or self._form_dialog is None
        ):
            return
        control = self._form.get("identity_file")
        if isinstance(control, ft.TextField):
            control.value = files[0].path
            control.update()
        self._update_preview(None)

    def _save_form(
        self,
        _: object,
        *,
        generation: int | None = None,
    ) -> None:
        if generation is not None and generation != self._form_generation:
            return
        error_control = self._form.get("error")
        try:
            config = self._form_config()
        except ValueError as exc:
            self._set_form_error(str(exc) or "端口必须填写为整数")
            return
        try:
            self.view_model.save_config(
                config,
                editing=self._editing_id is not None,
            )
        except ValueError as exc:
            self._set_form_error(str(exc))
            return
        except ViewModelError as exc:
            self._toast(str(exc), error=True)
            return
        if isinstance(error_control, ft.Text):
            error_control.value = ""
        self._close_dialog(generation=generation)
        self._render()
        self._toast("隧道配置已保存")

    def _set_form_error(self, message: str) -> None:
        control = self._form.get("error")
        if isinstance(control, ft.Text):
            control.value = message
            control.update()

    def _close_dialog(self, *, generation: int | None = None) -> None:
        if generation is not None and generation != self._form_generation:
            return
        if self._form_dialog:
            self.page.close(self._form_dialog)
        self._form_dialog = None
        self._form_generation += 1
        self._file_picker_generation = None

    def _toggle(self, tunnel_id: str, enabled: bool) -> None:
        self.view_model.request_tunnel_state(tunnel_id, enabled)

    def _edit(self, tunnel_id: str) -> None:
        snapshot = self.view_model.snapshot(tunnel_id)
        if not snapshot:
            return
        if snapshot.state in {
            TunnelState.CONNECTING,
            TunnelState.CONNECTED,
            TunnelState.STOPPING,
        }:
            self._toast("请先断开隧道，再编辑配置", error=True)
            return
        self._open_form(snapshot.config)

    def _copy_command(self, config: TunnelConfig) -> None:
        try:
            self.page.set_clipboard(self.view_model.command_preview(config))
            self._toast("SSH 命令已复制")
        except Exception as exc:
            self._toast(f"复制失败：{exc}", error=True)

    def _show_logs(self, tunnel_id: str) -> None:
        self.view_model.set_log_filter(tunnel_id)
        self._change_view("logs")

    def _confirm_delete(self, tunnel_id: str) -> None:
        snapshot = self.view_model.snapshot(tunnel_id)
        if not snapshot:
            return
        if snapshot.state in {
            TunnelState.CONNECTING,
            TunnelState.CONNECTED,
            TunnelState.STOPPING,
        }:
            self._toast("请先断开隧道，再删除配置", error=True)
            return
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Container(
                        width=44,
                        height=44,
                        border_radius=12,
                        bgcolor=RED_SOFT,
                        border=ft.border.all(1, ft.Colors.with_opacity(0.24, RED)),
                        alignment=ft.alignment.center,
                        content=ft.Icon(
                            ft.Icons.DELETE_OUTLINE_ROUNDED, color=RED, size=22
                        ),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "删除隧道？",
                                color=TEXT,
                                size=19,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text("请确认这条配置不再需要", color=MUTED, size=12),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=12,
            ),
            content=ft.Container(
                width=430,
                padding=16,
                border_radius=12,
                bgcolor=RED_SOFT,
                border=ft.border.all(1, ft.Colors.with_opacity(0.24, RED)),
                content=ft.Text(
                    f"“{snapshot.config.name}”的配置将被删除，此操作不可撤销。",
                    color=TEXT_SECONDARY,
                    size=13,
                ),
            ),
            **dialog_surface_style(
                "删除隧道确认",
                shadow_opacity=0.24,
            ),
            actions=[
                ft.OutlinedButton(
                    "取消",
                    height=44,
                    style=self._secondary_button_style(),
                    on_click=lambda _: self.page.close(dialog),
                ),
                ft.ElevatedButton(
                    "删除",
                    icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                    height=44,
                    style=self._danger_button_style(),
                    on_click=lambda _: self._delete(tunnel_id, dialog),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dialog)

    def _delete(self, tunnel_id: str, dialog: ft.AlertDialog) -> None:
        try:
            self.view_model.delete_config(tunnel_id)
        except ViewModelError as exc:
            self._toast(str(exc), error=True)
            return
        self.page.close(dialog)
        self._render()
        self._toast("隧道已删除")

    def _open_service(self, snapshot: RuntimeSnapshot, forward: LocalForward) -> None:
        try:
            endpoint = self.view_model.open_forward(forward)
            if endpoint is not None:
                self.page.set_clipboard(endpoint)
                self._toast("本地服务地址已复制")
        except (OSError, RuntimeError) as exc:
            self._toast(str(exc), error=True)

    def _search_changed(self, event: object) -> None:
        control = getattr(event, "control", None)
        self.view_model.set_search_query(str(getattr(control, "value", "")))
        self._render()

    def _clear_search(self, _: object) -> None:
        self.view_model.set_search_query("")
        self._render()

    @staticmethod
    def _endpoint_key(host: str, port: int) -> tuple[str, int]:
        return EasyTunnelViewModel.endpoint_key(host, port)

    def _log_filter_changed(self, event: object) -> None:
        value = str(getattr(getattr(event, "control", None), "value", "all"))
        self.view_model.set_log_filter(None if value == "all" else value)
        self._render()

    def _persist(self) -> bool:
        try:
            self.view_model.persist()
            return True
        except ViewModelError as exc:
            self._toast(str(exc), error=True)
            return False

    def _toast(self, message: str, *, error: bool = False) -> None:
        color = RED_ACTIVE if error else PRIMARY_ACTIVE
        icon = (
            ft.Icons.ERROR_OUTLINE_ROUNDED if error else ft.Icons.INFO_OUTLINE_ROUNDED
        )
        self.page.open(
            ft.SnackBar(
                content=ft.Row(
                    [
                        ft.Icon(icon, color=SURFACE, size=20),
                        ft.Text(message, color=SURFACE, size=13, expand=True),
                    ],
                    spacing=10,
                ),
                bgcolor=color,
                behavior=ft.SnackBarBehavior.FLOATING,
                show_close_icon=True,
                close_icon_color=SURFACE,
                margin=18,
                padding=ft.padding.symmetric(horizontal=16, vertical=14),
                elevation=12,
                shape=ft.RoundedRectangleBorder(radius=16),
                duration=5000 if error else 3500,
            )
        )

    def _default_update_message(self) -> str:
        return self.view_model.default_update_message()

    def _request_update_check(self) -> None:
        if self._checking_update:
            return
        self.page.run_task(self._check_for_update, True)

    async def _check_for_update(self, manual: bool = False) -> None:
        if self._checking_update:
            return
        if not self.view_model.begin_update_check():
            if self.current_view == "settings":
                self._render()
            if manual:
                self._toast(self._update_status)
            return

        if self.current_view == "settings":
            self._render()
        result = await asyncio.to_thread(
            self.view_model.complete_update_check,
            __version__,
        )
        if result.is_error:
            if manual:
                self._toast(result.message, error=True)
        elif result.update is None:
            if manual:
                self._toast(result.message)
        else:
            self._show_update_dialog(result.update)
        if self.current_view == "settings":
            self._render()

    def _show_update_dialog(self, update: UpdateInfo) -> None:
        notes = update.release_notes.strip() or "此版本暂无发布说明。"
        if len(notes) > 360:
            notes = f"{notes[:360].rstrip()}…"
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Container(
                        width=48,
                        height=48,
                        border_radius=12,
                        gradient=ft.LinearGradient(
                            begin=ft.alignment.top_left,
                            end=ft.alignment.bottom_right,
                            colors=[PRIMARY_ACTIVE, PRIMARY, PRIMARY_LIGHT],
                        ),
                        alignment=ft.alignment.center,
                        content=ft.Icon(
                            ft.Icons.SYSTEM_UPDATE_ALT_ROUNDED,
                            color=SURFACE,
                            size=24,
                        ),
                    ),
                    ft.Column(
                        [
                            ft.Text(
                                "发现 EasyTunnel 新版本",
                                color=TEXT,
                                size=19,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text("稳定版本已准备好下载", color=MUTED, size=12),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Container(
                        padding=ft.padding.symmetric(horizontal=10, vertical=6),
                        border_radius=999,
                        bgcolor=PRIMARY_SOFT,
                        border=ft.border.all(1, BORDER),
                        content=ft.Text(
                            f"v{update.version}",
                            color=PRIMARY,
                            size=12,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    [
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=14, vertical=11),
                            border_radius=12,
                            bgcolor=PRIMARY_SOFT,
                            border=ft.border.all(1, BORDER),
                            content=ft.Row(
                                [
                                    ft.Icon(
                                        ft.Icons.VERIFIED_USER_OUTLINED,
                                        color=PRIMARY,
                                        size=20,
                                    ),
                                    ft.Text(
                                        "安装包下载完成并通过 SHA-256 校验后，"
                                        "才会启动更新程序。",
                                        color=TEXT_SECONDARY,
                                        size=12,
                                        expand=True,
                                    ),
                                ],
                                spacing=9,
                            ),
                        ),
                        ft.Text(
                            "版本说明",
                            color=TEXT,
                            size=13,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Container(
                            height=150,
                            padding=14,
                            border_radius=12,
                            bgcolor=INSET,
                            border=ft.border.all(1, BORDER),
                            content=ft.Column(
                                [
                                    ft.Text(
                                        notes,
                                        color=TEXT_SECONDARY,
                                        size=12,
                                        selectable=True,
                                    )
                                ],
                                scroll=ft.ScrollMode.AUTO,
                            ),
                        ),
                    ],
                    spacing=12,
                    tight=True,
                ),
            ),
            **dialog_surface_style("软件更新"),
            actions=[
                ft.OutlinedButton(
                    "稍后更新",
                    height=44,
                    style=self._secondary_button_style(),
                    on_click=lambda _: self.page.close(dialog),
                ),
                ft.ElevatedButton(
                    "下载并安装",
                    icon=ft.Icons.SYSTEM_UPDATE_ALT_ROUNDED,
                    height=44,
                    style=self._primary_button_style(),
                    on_click=lambda _: self._start_update_install(dialog, update),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dialog)

    def _start_update_install(self, dialog: ft.AlertDialog, update: UpdateInfo) -> None:
        self.page.close(dialog)
        self.page.run_task(self._download_and_launch_update, update)

    async def _download_and_launch_update(self, update: UpdateInfo) -> None:
        self._toast(f"正在下载 EasyTunnel {update.version} 更新包…")
        try:
            await asyncio.to_thread(self.view_model.install_update, update)
        except ViewModelError as exc:
            self._toast(str(exc), error=True)
            return

        self._toast("更新程序已启动，应用即将关闭。")
        self.page.window.close()

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
        return self.view_model.runtime_fingerprint()

    @staticmethod
    def _is_loopback(host: str) -> bool:
        return EasyTunnelViewModel.is_loopback(host)

    def _on_disconnect(self, _: object) -> None:
        self.view_model.shutdown()
