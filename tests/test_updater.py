from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from packaging.version import Version

from easytunnel import updater
from easytunnel.updater import (
    UpdateError,
    UpdateInfo,
    download_installer,
    fetch_latest_update,
    parse_latest_release,
)


class _Response(BytesIO):
    def __init__(
        self,
        content: bytes = b"",
        *,
        url: str = "https://example.test/response",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(content)
        self._url = url
        self.headers = headers or {}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def geturl(self) -> str:
        return self._url


def _release(version: str, assets: list[dict[str, object]]) -> dict[str, object]:
    return {
        "tag_name": f"v{version}",
        "html_url": (
            "https://github.com/SolitudeKing/easy-tunnel/releases/tag/"
            f"v{version}"
        ),
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
    update = parse_latest_release(
        _release("0.2.0", [_installer_asset("0.2.0")]),
        "0.1.0",
    )

    assert update is not None
    assert update.version == Version("0.2.0")
    assert update.installer_name == "EasyTunnel-Setup-0.2.0.exe"
    assert update.sha256 == "a" * 64


def test_detects_flet_packaged_windows_runtime() -> None:
    production_environment = {
        "FLET_PLATFORM": "windows",
        "FLET_APP_STORAGE_DATA": r"C:\Users\tester\Documents\flet\easytunnel",
    }

    assert updater._is_packaged_windows_runtime("nt", production_environment)
    assert not updater._is_packaged_windows_runtime("posix", production_environment)
    assert not updater._is_packaged_windows_runtime(
        "nt",
        {"FLET_ASSETS_DIR": r"C:\project\assets"},
    )


def test_ignores_current_or_older_release() -> None:
    release = _release("0.1.0", [_installer_asset("0.1.0")])

    assert parse_latest_release(release, "0.1.0") is None
    assert parse_latest_release(release, "0.2.0") is None


@pytest.mark.parametrize(
    "digest",
    [
        "invalid",
        f"{'a' * 30}  {'a' * 32}",
    ],
)
def test_rejects_new_release_without_valid_installer_digest(digest: str) -> None:
    release = _release("0.2.0", [_installer_asset("0.2.0", digest=digest)])

    with pytest.raises(UpdateError, match="SHA-256"):
        parse_latest_release(release, "0.1.0")


def test_ignores_prerelease() -> None:
    release = _release("0.2.0", [_installer_asset("0.2.0")])
    release["prerelease"] = True

    assert parse_latest_release(release, "0.1.0") is None


def test_rejects_installer_larger_than_safety_limit() -> None:
    asset = _installer_asset("0.2.0")
    asset["size"] = updater.MAX_INSTALLER_SIZE + 1

    with pytest.raises(UpdateError, match="最大允许大小"):
        parse_latest_release(_release("0.2.0", [asset]), "0.1.0")


def test_falls_back_to_release_assets_when_api_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installer_name = "EasyTunnel-Setup-0.2.0.exe"
    checksum = "a" * 64
    responses: list[object] = [
        HTTPError(
            updater.GITHUB_LATEST_RELEASE_URL,
            403,
            "rate limit exceeded",
            {},
            None,
        ),
        _Response(
            url="https://github.com/SolitudeKing/easy-tunnel/releases/tag/v0.2.0",
        ),
        _Response(f"{checksum} *{installer_name}\n".encode("ascii")),
    ]
    requests: list[Request] = []

    def fake_urlopen(request: Request, **_: object) -> object:
        requests.append(request)
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(updater, "urlopen", fake_urlopen)

    update = fetch_latest_update("0.1.1")

    assert update is not None
    assert update.version == Version("0.2.0")
    assert update.installer_name == installer_name
    assert update.sha256 == checksum
    assert update.installer_size is None
    assert len(requests) == 3
    assert requests[1].get_method() == "HEAD"


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

    monkeypatch.setattr(
        updater,
        "urlopen",
        lambda *_args, **_kwargs: _Response(content),
    )

    installer = download_installer(update, tmp_path)

    assert installer.read_bytes() == content


def test_download_stops_when_installer_exceeds_expected_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = UpdateInfo(
        version=Version("0.2.0"),
        installer_name="EasyTunnel-Setup-0.2.0.exe",
        installer_url="https://example.test/EasyTunnel-Setup.exe",
        sha256="a" * 64,
        installer_size=3,
        release_url="https://example.test/release",
        release_notes="",
    )
    monkeypatch.setattr(
        updater,
        "urlopen",
        lambda *_args, **_kwargs: _Response(b"too large"),
    )

    with pytest.raises(UpdateError, match="大小"):
        download_installer(update, tmp_path)

    assert not (tmp_path / update.installer_name).exists()
    assert not list(tmp_path.iterdir())


def test_download_limits_installer_without_declared_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = UpdateInfo(
        version=Version("0.2.0"),
        installer_name="EasyTunnel-Setup-0.2.0.exe",
        installer_url="https://example.test/EasyTunnel-Setup.exe",
        sha256="a" * 64,
        installer_size=None,
        release_url="https://example.test/release",
        release_notes="",
    )
    monkeypatch.setattr(updater, "MAX_INSTALLER_SIZE", 4)
    monkeypatch.setattr(
        updater,
        "urlopen",
        lambda *_args, **_kwargs: _Response(b"12345"),
    )

    with pytest.raises(UpdateError, match="最大允许大小"):
        download_installer(update, tmp_path)

    assert not list(tmp_path.iterdir())


def test_download_cleans_partial_file_after_network_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = UpdateInfo(
        version=Version("0.2.0"),
        installer_name="EasyTunnel-Setup-0.2.0.exe",
        installer_url="https://example.test/EasyTunnel-Setup.exe",
        sha256="a" * 64,
        installer_size=3,
        release_url="https://example.test/release",
        release_notes="",
    )

    def fail_download(*_: object, **__: object) -> None:
        raise OSError("network unavailable")

    monkeypatch.setattr(updater, "urlopen", fail_download)

    with pytest.raises(UpdateError, match="无法下载安装包"):
        download_installer(update, tmp_path)

    assert not list(tmp_path.iterdir())


def test_download_wraps_destination_creation_error(tmp_path: Path) -> None:
    destination = tmp_path / "not-a-directory"
    destination.write_text("occupied", encoding="utf-8")
    update = UpdateInfo(
        version=Version("0.2.0"),
        installer_name="EasyTunnel-Setup-0.2.0.exe",
        installer_url="https://example.test/EasyTunnel-Setup.exe",
        sha256="a" * 64,
        installer_size=3,
        release_url="https://example.test/release",
        release_notes="",
    )

    with pytest.raises(UpdateError, match="无法下载安装包"):
        download_installer(update, destination)
