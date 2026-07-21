"""Shared Mist Sea Salt dialog surface options."""

from __future__ import annotations

import flet as ft

from ..widget.theme import PRIMARY, SURFACE, TEXT


def dialog_surface_style(
    semantics_label: str,
    *,
    content_padding: object | None = None,
    actions_top: int = 18,
    shadow_opacity: float = 0.28,
) -> dict[str, object]:
    """Return consistent visual and accessibility options for dialogs."""

    return {
        "bgcolor": SURFACE,
        "surface_tint_color": SURFACE,
        "barrier_color": ft.Colors.with_opacity(0.36, TEXT),
        "shadow_color": ft.Colors.with_opacity(shadow_opacity, PRIMARY),
        "elevation": 24,
        "shape": ft.RoundedRectangleBorder(radius=24),
        "inset_padding": 24,
        "title_padding": ft.padding.only(
            left=20,
            top=20,
            right=20,
            bottom=14,
        ),
        "content_padding": content_padding
        if content_padding is not None
        else ft.padding.symmetric(horizontal=20),
        "actions_padding": ft.padding.only(
            left=20,
            top=actions_top,
            right=20,
            bottom=20,
        ),
        "clip_behavior": ft.ClipBehavior.ANTI_ALIAS,
        "semantics_label": semantics_label,
    }
