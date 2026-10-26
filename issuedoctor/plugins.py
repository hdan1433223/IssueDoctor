"""Plugin discovery and registration.

IssueDoctor's core (collection, scoring, reporting) is deliberately independent
of any optional heavy dependency. Optional capabilities — local embedding
models, server-side PDF rendering, LLM semantic analysis — are expressed as
*plugins* that are discovered at runtime.

Two discovery mechanisms are supported:

1. **Entry points** — third-party packages advertise plugins under the
   ``issuedoctor.plugins`` group. This is how external extensions register.
2. **Built-in registry** — the plugins shipped in ``issuedoctor/plugins/`` are
   registered explicitly so they work without installation.

A plugin declares its capability requirements; the loader skips (rather than
fails on) plugins whose optional dependencies are absent, recording the reason
so the UI can explain what is unavailable.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from issuedoctor.capabilities import probe

#: Entry point group that third-party plugins register under.
ENTRY_POINT_GROUP = "issuedoctor.plugins"


@runtime_checkable
class Plugin(Protocol):
    """Contract every plugin must satisfy."""

    #: Stable machine name, e.g. ``"vector"``.
    name: str
    #: Human-readable label shown in the UI.
    label: str
    #: Optional capability this plugin needs, or None if always usable.
    requires: str | None


@dataclass(frozen=True)
class LoadedPlugin:
    """A plugin together with its availability verdict."""

    name: str
    label: str
    available: bool
    reason: str = ""
    install_hint: str = ""
    factory: Any = None
    metadata: dict = field(default_factory=dict)

    def build(self):
        """Instantiate the plugin, ensuring it is usable first.

        A callable factory is invoked; anything else is returned as-is. This
        lets plugins register either a ready object or a constructor that
        defers importing its optional dependency until the plugin is used.
        """
        if not self.available:
            raise PluginUnavailable(self.name, self.reason, self.install_hint)
        return self.factory() if callable(self.factory) else self.factory


class PluginUnavailable(RuntimeError):
    """Raised when building a plugin whose optional dependency is missing."""

    def __init__(self, name: str, reason: str, install_hint: str = "") -> None:
        self.name = name
        self.reason = reason
        self.install_hint = install_hint
        detail = f"：{reason}" if reason else ""
        hint = f" 安装方式：{install_hint}" if install_hint else ""
        super().__init__(f"插件「{name}」当前不可用{detail}。{hint}".strip())


@dataclass(frozen=True)
class PluginSpec:
    """Declarative description of a built-in plugin."""

    name: str
    label: str
    requires: str | None
    factory: Any
    metadata: dict = field(default_factory=dict)


def _evaluate(spec: PluginSpec) -> LoadedPlugin:
    if spec.requires is None:
        return LoadedPlugin(
            name=spec.name,
            label=spec.label,
            available=True,
            factory=spec.factory,
            metadata=dict(spec.metadata),
        )
    status = probe(spec.requires)
    return LoadedPlugin(
        name=spec.name,
        label=spec.label,
        available=status.available,
        reason=(
            ""
            if status.available
            else f"缺少依赖 {('、'.join(status.missing))}"
        ),
        install_hint=status.install_hint,
        factory=spec.factory,
        metadata=dict(spec.metadata),
    )


def builtin_specs() -> list[PluginSpec]:
    """Built-in plugin declarations.

    Imported lazily inside the function so that plugin discovery itself never
    drags in an optional dependency.
    """
    specs: list[PluginSpec] = []

    def vector_factory():
        from issuedoctor.embedding.model_manager import EmbeddingModelManager

        return EmbeddingModelManager

    def pdf_factory():
        from issuedoctor.exports.pdf_exporter import _playwright_renderer

        return _playwright_renderer

    specs.append(
        PluginSpec(
            name="vector",
            label="本地语义向量",
            requires="vector",
            factory=vector_factory,
            metadata={
                "description": "使用 sentence-transformers 本地模型提升重复问题检测精度",
            },
        )
    )
    specs.append(
        PluginSpec(
            name="pdf",
            label="服务端 PDF 导出",
            requires="pdf",
            factory=pdf_factory,
            metadata={
                "description": "后端直接渲染 PDF；未启用时可用浏览器打印导出",
            },
        )
    )
    return specs


def _load_entry_point_plugins() -> list[LoadedPlugin]:
    """Discover third-party plugins advertised via entry points."""
    loaded: list[LoadedPlugin] = []
    try:
        entry_points = importlib.metadata.entry_points()
        selected = (
            entry_points.select(group=ENTRY_POINT_GROUP)
            if hasattr(entry_points, "select")
            else entry_points.get(ENTRY_POINT_GROUP, [])
        )
    except Exception:  # pragma: no cover - defensive, metadata may be absent
        return loaded

    for entry_point in selected:
        try:
            target = entry_point.load()
            spec = target() if callable(target) and not isinstance(target, PluginSpec) else target
            if isinstance(spec, PluginSpec):
                loaded.append(_evaluate(spec))
        except Exception as exc:  # pragma: no cover - a broken plugin must not break startup
            loaded.append(
                LoadedPlugin(
                    name=getattr(entry_point, "name", "unknown"),
                    label=getattr(entry_point, "name", "unknown"),
                    available=False,
                    reason=f"插件加载失败：{type(exc).__name__}",
                )
            )
    return loaded


def discover_plugins() -> list[LoadedPlugin]:
    """Return every known plugin with its availability verdict.

    Built-in plugins come first, then any third-party entry-point plugins.
    """
    plugins = [_evaluate(spec) for spec in builtin_specs()]
    plugins.extend(_load_entry_point_plugins())
    return plugins


def plugin_map() -> dict[str, LoadedPlugin]:
    """Plugins keyed by name for quick lookup."""
    return {plugin.name: plugin for plugin in discover_plugins()}


def summary() -> list[dict]:
    """Serialisable plugin status list for the settings/diagnostics UI."""
    return [
        {
            "name": plugin.name,
            "label": plugin.label,
            "available": plugin.available,
            "reason": plugin.reason,
            "install_hint": plugin.install_hint,
            "description": plugin.metadata.get("description", ""),
        }
        for plugin in discover_plugins()
    ]
