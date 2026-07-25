from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "agent_context_lens"
FORBIDDEN_PRODUCT_IMPORTS = {
    "http",
    "requests",
    "socket",
    "subprocess",
    "tomli",
    "tomllib",
    "urllib",
}


def test_runtime_declares_no_dependencies():
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.10"' in metadata
    assert "dependencies = []" in metadata


def test_product_path_has_no_network_process_or_toml_imports():
    imported: set[str] = set()
    for source_path in SOURCE.rglob("*.py"):
        tree = ast.parse(
            source_path.read_text(encoding="utf-8"),
            filename=str(source_path),
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(
                    alias.name.partition(".")[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.partition(".")[0])

    assert imported.isdisjoint(FORBIDDEN_PRODUCT_IMPORTS)
