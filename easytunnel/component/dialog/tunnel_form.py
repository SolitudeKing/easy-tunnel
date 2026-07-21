"""Control references for one dynamically added tunnel-forward form row."""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass(slots=True)
class ForwardFormRow:
    forward_id: str
    name: ft.TextField
    service_type: ft.Dropdown
    bind_host: ft.TextField
    local_port: ft.TextField
    remote_host: ft.TextField
    remote_port: ft.TextField
    title: ft.Text
    delete_button: ft.IconButton
    container: ft.Container
