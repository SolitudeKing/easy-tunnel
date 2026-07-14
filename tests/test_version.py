import pytest

from easytunnel import __version__
from easytunnel.__main__ import run


def test_version_command_prints_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        run(["--version"])

    assert error.value.code == 0
    assert capsys.readouterr().out == f"easytunnel {__version__}\n"
