"""Shell-safe formatting helpers used for command previews."""

from __future__ import annotations


def powershell_join(arguments: list[str]) -> str:
    """Render arguments as a PowerShell command without evaluating them."""

    def quote(argument: str) -> str:
        return "'" + argument.replace("'", "''") + "'"

    return "& " + " ".join(quote(argument) for argument in arguments)
