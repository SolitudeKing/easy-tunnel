"""Mist Sea Salt design tokens and reusable Flet styles."""

from __future__ import annotations

import flet as ft


BG = "#F5FAFF"
BG_SECONDARY = "#EAF4FB"
SURFACE = "#FFFFFF"
SURFACE_MUTED = "#F0F8FC"
INSET = "#E6F1F8"
HOVER = "#DCEEF8"
DISABLED = "#E1EAF0"
SIDEBAR = BG_SECONDARY
TEXT = "#203846"
TEXT_SECONDARY = "#3D5C6C"
MUTED = "#587485"
PRIMARY = "#2F6F92"
PRIMARY_HOVER = "#255E7C"
PRIMARY_ACTIVE = "#1B4D68"
PRIMARY_LIGHT = "#3C7C9E"
PRIMARY_SOFT = "#D7ECF7"
GREEN = "#25723F"
GREEN_SOFT = "#E9F5ED"
AMBER = "#875B15"
AMBER_SOFT = "#FFF4D8"
RED = "#B42318"
RED_HOVER = "#941C14"
RED_ACTIVE = "#7A1812"
RED_SOFT = "#FBEAE8"
BORDER = "#D4E5EF"
BORDER_STRONG = "#6E93A6"

FORM_BG = BG
FORM_BG_SECONDARY = BG_SECONDARY
FORM_CARD = SURFACE_MUTED
FORM_SURFACE = SURFACE
FORM_INSET = INSET
FORM_HOVER = HOVER
FORM_TEXT = TEXT
FORM_TEXT_SECONDARY = TEXT_SECONDARY
FORM_MUTED = MUTED
FORM_ACCENT = PRIMARY
FORM_ACCENT_HOVER = PRIMARY_HOVER
FORM_ACCENT_ACTIVE = PRIMARY_ACTIVE
FORM_ACCENT_LIGHT = PRIMARY_LIGHT
FORM_ACCENT_SOFT = PRIMARY_SOFT
FORM_BORDER = BORDER
FORM_BORDER_STRONG = BORDER_STRONG
FORM_SUCCESS = GREEN
FORM_DANGER = RED
FORM_DANGER_SOFT = RED_SOFT


def build_theme() -> ft.Theme:
    """Build the shared light Mist Sea Salt theme."""

    return ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=PRIMARY,
            on_primary=SURFACE,
            primary_container=PRIMARY_SOFT,
            on_primary_container=TEXT,
            secondary=PRIMARY_LIGHT,
            on_secondary=SURFACE,
            secondary_container=BG_SECONDARY,
            on_secondary_container=TEXT,
            error=RED,
            on_error=SURFACE,
            error_container=RED_SOFT,
            on_error_container=RED,
            background=BG,
            on_background=TEXT,
            surface=SURFACE,
            on_surface=TEXT,
            surface_variant=SURFACE_MUTED,
            on_surface_variant=TEXT_SECONDARY,
            outline=BORDER_STRONG,
            outline_variant=BORDER,
            shadow=PRIMARY_ACTIVE,
            scrim=TEXT,
            inverse_surface=PRIMARY_ACTIVE,
            on_inverse_surface=SURFACE,
            inverse_primary=PRIMARY_SOFT,
            surface_tint=SURFACE,
            surface_bright=SURFACE,
            surface_container=SURFACE_MUTED,
            surface_container_high=BG_SECONDARY,
            surface_container_low=BG,
            surface_container_lowest=SURFACE,
        ),
        font_family="Segoe UI",
        use_material3=True,
        scaffold_bgcolor=BG,
        canvas_color=BG,
        divider_color=BORDER,
        dialog_theme=ft.DialogTheme(
            bgcolor=SURFACE,
            surface_tint_color=SURFACE,
            shadow_color=ft.Colors.with_opacity(0.28, PRIMARY),
            barrier_color=ft.Colors.with_opacity(0.36, TEXT),
            shape=ft.RoundedRectangleBorder(radius=24),
        ),
        focus_color=ft.Colors.with_opacity(0.24, PRIMARY),
        hover_color=ft.Colors.with_opacity(0.08, PRIMARY),
    )


def panel_shadow() -> ft.BoxShadow:
    return ft.BoxShadow(
        blur_radius=24,
        color=ft.Colors.with_opacity(0.12, PRIMARY_LIGHT),
        offset=ft.Offset(0, 8),
    )


def primary_button_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color={
            ft.ControlState.DEFAULT: SURFACE,
            ft.ControlState.DISABLED: MUTED,
        },
        bgcolor={
            ft.ControlState.DEFAULT: PRIMARY,
            ft.ControlState.HOVERED: PRIMARY_HOVER,
            ft.ControlState.PRESSED: PRIMARY_ACTIVE,
            ft.ControlState.DISABLED: DISABLED,
        },
        overlay_color={
            ft.ControlState.HOVERED: ft.Colors.with_opacity(0.08, SURFACE),
            ft.ControlState.FOCUSED: ft.Colors.with_opacity(0.18, SURFACE),
            ft.ControlState.PRESSED: ft.Colors.with_opacity(0.12, SURFACE),
        },
        side={
            ft.ControlState.DEFAULT: ft.BorderSide(1, PRIMARY),
            ft.ControlState.FOCUSED: ft.BorderSide(2, SURFACE),
            ft.ControlState.DISABLED: ft.BorderSide(1, BORDER),
        },
        elevation={
            ft.ControlState.DEFAULT: 0,
            ft.ControlState.HOVERED: 2,
            ft.ControlState.PRESSED: 0,
            ft.ControlState.DISABLED: 0,
        },
        shadow_color=ft.Colors.with_opacity(0.28, PRIMARY),
        shape=ft.RoundedRectangleBorder(radius=12),
        padding=ft.padding.symmetric(horizontal=18, vertical=12),
        animation_duration=150,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_600),
    )


def secondary_button_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color={
            ft.ControlState.DEFAULT: TEXT_SECONDARY,
            ft.ControlState.HOVERED: PRIMARY,
            ft.ControlState.PRESSED: PRIMARY_ACTIVE,
            ft.ControlState.DISABLED: MUTED,
        },
        bgcolor={
            ft.ControlState.DEFAULT: SURFACE,
            ft.ControlState.HOVERED: BG_SECONDARY,
            ft.ControlState.PRESSED: INSET,
            ft.ControlState.DISABLED: SURFACE_MUTED,
        },
        side={
            ft.ControlState.DEFAULT: ft.BorderSide(1, BORDER_STRONG),
            ft.ControlState.FOCUSED: ft.BorderSide(2, PRIMARY),
            ft.ControlState.DISABLED: ft.BorderSide(1, BORDER),
        },
        shape=ft.RoundedRectangleBorder(radius=12),
        padding=ft.padding.symmetric(horizontal=16, vertical=10),
        animation_duration=150,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_600),
    )


def danger_button_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color={
            ft.ControlState.DEFAULT: SURFACE,
            ft.ControlState.DISABLED: MUTED,
        },
        bgcolor={
            ft.ControlState.DEFAULT: RED,
            ft.ControlState.HOVERED: RED_HOVER,
            ft.ControlState.PRESSED: RED_ACTIVE,
            ft.ControlState.DISABLED: DISABLED,
        },
        side={
            ft.ControlState.DEFAULT: ft.BorderSide(1, RED),
            ft.ControlState.FOCUSED: ft.BorderSide(2, SURFACE),
            ft.ControlState.DISABLED: ft.BorderSide(1, BORDER),
        },
        elevation=0,
        shape=ft.RoundedRectangleBorder(radius=12),
        padding=ft.padding.symmetric(horizontal=18, vertical=12),
        animation_duration=150,
        text_style=ft.TextStyle(weight=ft.FontWeight.W_600),
    )
