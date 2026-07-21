from __future__ import annotations

import ast
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).parents[1] / "easytunnel"

FORBIDDEN_IMPORTS = {
    "model": {"component", "flet", "repository", "service", "view", "viewmodel"},
    "repository": {"component", "flet", "service", "view", "viewmodel"},
    "service": {"component", "flet", "repository", "view", "viewmodel"},
    "utils": {"component", "flet", "repository", "service", "view", "viewmodel"},
    "config": {"component", "flet", "repository", "service", "view", "viewmodel"},
    "viewmodel": {"component", "flet", "view"},
    "view": {"repository", "service"},
}


def _import_root(node: ast.Import | ast.ImportFrom) -> set[str]:
    if isinstance(node, ast.Import):
        roots: set[str] = set()
        for alias in node.names:
            parts = alias.name.split(".")
            roots.add(
                parts[1] if parts[0] == "easytunnel" and len(parts) > 1 else parts[0]
            )
        return roots
    if not node.module:
        return set()
    parts = node.module.split(".")
    return {parts[1] if parts[0] == "easytunnel" and len(parts) > 1 else parts[0]}


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_IMPORTS))
def test_layer_does_not_import_forbidden_dependencies(layer: str) -> None:
    violations: list[str] = []
    for path in (PACKAGE_ROOT / layer).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            forbidden = _import_root(node) & FORBIDDEN_IMPORTS[layer]
            for dependency in sorted(forbidden):
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno} imports {dependency}"
                )

    assert not violations, "\n".join(violations)


def test_all_mvvm_directories_are_python_packages() -> None:
    packages = (
        "component",
        "component/dialog",
        "component/widget",
        "view",
        "viewmodel",
        "model",
        "repository",
        "service",
        "utils",
        "config",
    )
    missing = [
        name for name in packages if not (PACKAGE_ROOT / name / "__init__.py").is_file()
    ]
    assert not missing
