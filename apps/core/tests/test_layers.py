"""The project layering rules: domain code is plain Python, queries live in
repositories, and views reach them only through use cases."""

import ast
from pathlib import Path

import pytest

APPS = Path(__file__).resolve().parents[2]
SHARED_HELPERS = {APPS / "core" / "repositories" / "keyset.py"}


def _modules(layer: str) -> list[Path]:
    return sorted(p for p in APPS.glob(f"*/{layer}/*.py") if p.name != "__init__.py")


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _orm_calls(path: Path) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Attribute) and node.attr == "objects"
    ]


@pytest.mark.parametrize("path", _modules("use_cases") + _modules("api"), ids=str)
def test_use_cases_and_views_never_query_the_orm(path):
    assert _orm_calls(path) == []


@pytest.mark.parametrize("path", _modules("domain"), ids=str)
def test_domain_imports_only_plain_python_and_other_domain_code(path):
    def forbidden(name: str) -> bool:
        if name.startswith(("django", "rest_framework")):
            return True
        return name.startswith("apps.") and ".domain." not in name

    assert [name for name in _imports(path) if forbidden(name)] == []


@pytest.mark.parametrize("path", _modules("api"), ids=str)
def test_views_reach_repositories_only_through_use_cases(path):
    assert [name for name in _imports(path) if ".repositories." in name] == []


@pytest.mark.parametrize(
    "path", [p for p in _modules("repositories") if p not in SHARED_HELPERS], ids=str
)
def test_each_repository_has_a_small_interface(path):
    protocols = [
        node.name
        for node in _tree(path).body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    ]
    assert protocols
