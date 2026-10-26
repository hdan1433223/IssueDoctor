"""Tests for the optional-capability probing layer."""

import ast
import pathlib

import pytest

from issuedoctor.capabilities import (
    INSTALL_HINTS,
    OptionalDependencyError,
    capability_report,
    is_available,
    probe,
    require,
)

#: Packages that must never be imported at module import time.
OPTIONAL_PACKAGES = {
    "numpy",
    "sklearn",
    "scipy",
    "torch",
    "sentence_transformers",
    "transformers",
    "playwright",
}

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[2] / "issuedoctor"


def test_every_capability_reports_a_name_and_hint():
    report = capability_report()
    names = {item["name"] for item in report}
    assert names == {"vector", "pdf"}
    for item in report:
        assert item["label"]
        assert isinstance(item["available"], bool)
        assert isinstance(item["missing"], list)
        assert item["install_hint"] == INSTALL_HINTS[item["name"]]


def test_probe_marks_absent_packages_without_importing_them():
    status = probe("vector")
    if status.available:
        assert status.missing == ()
    else:
        assert status.missing
        assert "sentence_transformers" in status.missing or "numpy" in status.missing


def test_unknown_capability_is_treated_as_always_available():
    # A capability with no declared requirements probes as available.
    assert is_available("does-not-exist") is True


def test_require_raises_actionable_error_when_dependency_missing(monkeypatch):
    monkeypatch.setattr(
        "issuedoctor.capabilities._module_exists",
        lambda _name: False,
    )
    try:
        require("pdf", "playwright.sync_api")
    except OptionalDependencyError as exc:
        assert exc.capability == "pdf"
        assert "playwright" in exc.missing
        assert "issuedoctor[pdf]" in str(exc)
    else:  # pragma: no cover - only reached if playwright is installed
        raise AssertionError("expected OptionalDependencyError")


def test_require_returns_module_when_available():
    import json

    assert require("does-not-exist", "json") is json


# --------------------------------------------------------------------------
# Architectural invariant
#
# The whole point of the capability layer is that a minimal installation can
# import every module. That only holds if no module imports an optional package
# at module scope. This test enforces the rule statically so a future edit
# cannot silently reintroduce a hard dependency.
# --------------------------------------------------------------------------


def _module_level_optional_imports() -> list[str]:
    offenders = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # top level only; nested imports are allowed
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.split(".")[0] in OPTIONAL_PACKAGES:
                    offenders.append(f"{path.name}:{node.lineno} -> {module}")
    return offenders


def test_no_module_imports_optional_dependency_at_module_scope():
    offenders = _module_level_optional_imports()
    assert offenders == [], (
        "以下模块在顶层导入了可选依赖，会让精简安装无法导入：\n  "
        + "\n  ".join(offenders)
    )


def test_every_optional_dependency_imported_by_code_has_a_capability():
    """Any optional package the code imports must be covered by a capability.

    Transitive dependencies (torch, scipy, ...) are pulled in by the packages
    we declare, so only packages actually imported by our own modules are
    checked.
    """
    declared = {
        package for packages in _required_packages().values() for package in packages
    }
    imported = _optional_packages_imported_anywhere()
    undeclared = imported - declared
    assert undeclared == set(), (
        f"以下可选依赖被代码导入但未纳入能力声明：{sorted(undeclared)}"
    )


def _optional_packages_imported_anywhere() -> set[str]:
    """Optional packages referenced by any import statement, at any depth."""
    found: set[str] = set()
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):  # include nested imports
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                root = module.split(".")[0]
                if root in OPTIONAL_PACKAGES:
                    found.add(root)
    return found


def _required_packages() -> dict[str, tuple[str, ...]]:
    from issuedoctor.capabilities import _REQUIRED_PACKAGES

    return _REQUIRED_PACKAGES


def test_probe_never_imports_the_heavy_package():
    """Probing must not pay the import cost of the package it checks."""
    import sys

    probe("vector")
    assert "torch" not in sys.modules
    assert "sentence_transformers" not in sys.modules
    assert "sentence_transformers" not in sys.modules


@pytest.mark.parametrize("capability", ["vector", "pdf"])
def test_capability_report_entries_are_complete(capability):
    entry = next(item for item in capability_report() if item["name"] == capability)
    assert entry["label"]
    assert entry["install_hint"].startswith("pip install")
    assert isinstance(entry["missing"], list)
