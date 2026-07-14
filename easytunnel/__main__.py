"""Command-line entry point for EasyTunnel."""

import argparse

from . import __version__


def run(argv: list[str] | None = None) -> None:
    """Run the EasyTunnel desktop application.

    Args:
        argv: Optional command-line arguments used instead of ``sys.argv``.
    """
    parser = argparse.ArgumentParser(prog="easytunnel")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args(argv)

    import flet as ft

    from .app import main

    ft.app(target=main)


if __name__ == "__main__":
    run()
