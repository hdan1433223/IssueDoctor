"""Optional runtime capabilities for IssueDoctor.

The core diagnostic pipeline (GitHub collection, six-dimension rule scoring,
report building, JSON/Markdown export) runs on a deliberately tiny dependency
set. Heavier capabilities are *optional* and are resolved lazily at call time so
that a minimal installation can start and complete a full audit.

Capability map
--------------
``vector``      Local semantic similarity via ``sentence-transformers``
                (pulls PyTorch). Without it, duplicate detection uses the
                built-in pure-Python hashing TF-IDF, which needs no third-party
                package at all.
``pdf``         Server-side PDF rendering via Playwright Chromium. Without it,
                the browser print page remains available.

Design rules
------------
* No module in ``issuedoctor`` may import an optional package at module import
  time. Import must live inside a function guarded by :func:`is_available`.
* Missing capabilities MUST degrade, never raise. Degradation is reported to
  the user through the audit result, not through an exception.
* Each capability reports an install hint so the UI can tell the user exactly
  how to enable it.
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass

#: pip extras that enable each optional capability.
INSTALL_HINTS: dict[str, str] = {
    "vector": 'pip install "issuedoctor[vector]"',
    "pdf": 'pip install "issuedoctor[pdf]"',
}

#: Packages probed for each capability, in order. A capability is available
#: when *every* required package resolves.
_REQUIRED_PACKAGES: dict[str, tuple[str, ...]] = {
    "vector": ("numpy", "sentence_transformers"),
    "pdf": ("playwright",),
}


@dataclass(frozen=True)
class CapabilityStatus:
    """Result of probing one optional capability."""

    name: str
    available: bool
    missing: tuple[str, ...] = ()
    install_hint: str = ""

    @property
    def label(self) -> str:
        return _CAPABILITY_LABELS.get(self.name, self.name)


_CAPABILITY_LABELS = {
    "vector": "本地语义向量",
    "pdf": "服务端 PDF 导出",
}


def _module_exists(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def probe(capability: str) -> CapabilityStatus:
    """Check whether an optional capability's dependencies are importable.

    ``find_spec`` is used instead of importing so that probing never pays the
    cost of loading a heavy package such as PyTorch.
    """
    required = _REQUIRED_PACKAGES.get(capability, ())
    missing = tuple(name for name in required if not _module_exists(name))
    return CapabilityStatus(
        name=capability,
        available=not missing,
        missing=missing,
        install_hint=INSTALL_HINTS.get(capability, ""),
    )


def is_available(capability: str) -> bool:
    """True when every dependency of ``capability`` can be imported."""
    return probe(capability).available


def require(capability: str, module_name: str):
    """Import ``module_name`` for ``capability``, or raise a soft error.

    Raises :class:`OptionalDependencyError` so the caller can degrade instead of
    crashing. Callers that can degrade should prefer :func:`is_available` first.
    """
    if not is_available(capability):
        raise OptionalDependencyError(capability)
    return importlib.import_module(module_name)


class OptionalDependencyError(RuntimeError):
    """Raised when an optional capability's dependencies are absent."""

    def __init__(self, capability: str) -> None:
        self.capability = capability
        status = probe(capability)
        self.missing = status.missing
        self.install_hint = status.install_hint
        detail = "、".join(status.missing) if status.missing else "未知依赖"
        super().__init__(
            f"可选能力「{status.label}」缺少依赖：{detail}。"
            f"安装方式：{status.install_hint}"
        )


def capability_report() -> list[dict]:
    """Snapshot of every optional capability, for the settings/diagnostics UI."""
    return [
        {
            "name": status.name,
            "label": status.label,
            "available": status.available,
            "missing": list(status.missing),
            "install_hint": status.install_hint,
        }
        for status in (probe(name) for name in _REQUIRED_PACKAGES)
    ]
