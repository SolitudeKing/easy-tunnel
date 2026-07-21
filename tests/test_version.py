import pytest
import flet as ft

from easytunnel import __version__
from easytunnel.__main__ import run
from easytunnel.config.paths import runtime_assets_directory


def test_version_command_prints_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        run(["--version"])

    assert error.value.code == 0
    assert capsys.readouterr().out == f"easytunnel {__version__}\n"


def test_command_entrypoint_passes_resolved_assets_to_flet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_app(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(ft, "app", fake_app)

    run([])

    assert captured["assets_dir"] == str(runtime_assets_directory())
    assert callable(captured["target"])
