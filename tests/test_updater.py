from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from packaging.version import Version

from easytunnel import updater
from easytunnel.updater import UpdateError, UpdateInfo, download_installer, parse_latest_release


def _release(version: str, assets: list[dict[str, object]]) -> dict[str, object]:
    return {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/SolitudeKing/easy-tunnel/releases/tag/v{version}",
        "body": "更新内容",
        "draft": False,
        "prerelease": False,
        "assets": assets,
    }


def _installer_asset(version: str, digest: str = "a" * 64) -> dict[str, object]:
    return {
        "name": f"EasyTunnel-Setup-{version}.exe",
        "browser_download_url": "https://example.test/EasyTunnel-Setup.exe",
        "digest": f"sha256:{digest}",
        "size": 3,
    }


def test_parses_newer_windows_installer() -> None:
    update = parse_latest_release(_release("0.2.0", [_installer_asset("0.2.0")]), "0.1.0")

    assert update is not None
    assert update.version == Version("0.2.0")
    assert update.installer_name == "EasyTunnel-Setup-0.2.0.exe"
    assert update.sha256 == "a" * 64


def test_ignores_current_or_older_release() -> None:
    release = _release("0.1.0", [_installer_asset("0.1.0")])

    assert parse_latest_release(release, "0.1.0") is None
    assert parse_latest_release(release, "0.2.0") is None


def test_rejects_new_release_without_valid_installer_digest() -> None:
    release = _release("0.2.0", [_installer_asset("0.2.0", digest="invalid")])

    with pytest.raises(UpdateError, match="SHA-256"):
        parse_latest_release(release, "0.1.0")


def test_ignores_prerelease() -> None:
    release = _release("0.2.0", [_installer_asset("0.2.0")])
    release["prerelease"] = True

    assert parse_latest_release(release, "0.1.0") is None


def test_download_verifies_installer_before_replacing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"new"
    update = UpdateInfo(
        version=Version("0.2.0"),
        installer_name="EasyTunnel-Setup-0.2.0.exe",
        installer_url="https://example.test/EasyTunnel-Setup.exe",
        sha256="11507a0e2f5e69d5dfa40a62a1bd7b6ee57e6bcd85c67c9b8431b36fff21c437",
        installer_size=len(content),
        release_url="https://example.test/release",
        release_notes="",
    )

    class _Response(BytesIO):
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_: object) -> None:
            self.close()

    monkeypatch.setattr(updater, "urlopen", lambda *_args, **_kwargs: _Response(content))

    installer = download_installer(update, tmp_path)

    assert installer.read_bytes() == content
