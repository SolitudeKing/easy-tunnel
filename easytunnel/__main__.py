import flet as ft

from .app import main


def run() -> None:
    ft.app(target=main)


if __name__ == "__main__":
    run()
