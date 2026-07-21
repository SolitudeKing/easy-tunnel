from __future__ import annotations

from pathlib import Path

import pytest

from easytunnel.config.paths import (
    APP_LOGO_ASSET,
    APP_WINDOW_ICON_ASSET,
    runtime_assets_directory,
)


def test_runtime_assets_directory_contains_semantic_assets() -> None:
    assets = runtime_assets_directory()

    assert (assets / APP_LOGO_ASSET).is_file()
    assert (assets / APP_WINDOW_ICON_ASSET).is_file()
    assert (assets / "icon.png").is_file()


def test_runtime_assets_directory_honors_explicit_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FLET_ASSETS_DIR", str(tmp_path))

    assert runtime_assets_directory() == tmp_path.resolve()


def test_python_distribution_declares_all_runtime_assets() -> None:
    project_root = Path(__file__).parents[1]
    document = (project_root / "pyproject.toml").read_text(encoding="utf-8")

    for asset in {
        "assets/icon.png",
        "assets/images/easytunnel-logo.png",
        "assets/icons/easytunnel.ico",
        "assets/icons/easytunnel.svg",
    }:
        assert f'"{asset}"' in document
