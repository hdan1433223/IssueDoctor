"""Tests for plugin discovery, availability verdicts and the CLI surface."""

from issuedoctor.plugins import (
    ENTRY_POINT_GROUP,
    LoadedPlugin,
    PluginSpec,
    PluginUnavailable,
    discover_plugins,
    plugin_map,
    summary,
)


def test_discovery_includes_builtin_plugins():
    names = {plugin.name for plugin in discover_plugins()}
    assert {"vector", "pdf"} <= names


def test_builtin_plugins_declare_capabilities_and_labels():
    for plugin in discover_plugins():
        if plugin.name in {"vector", "pdf"}:
            assert plugin.label
            assert plugin.metadata.get("description")


def test_plugin_without_requirements_is_always_available():
    plugin = LoadedPlugin(name="always", label="总是可用", available=True, factory=dict)
    assert plugin.available
    # A callable factory is instantiated by build().
    assert plugin.build() == {}
    assert isinstance(plugin.build(), dict)


def test_plugin_build_returns_non_callable_factory_as_is():
    sentinel = object()
    plugin = LoadedPlugin(name="raw", label="直接对象", available=True, factory=sentinel)
    assert plugin.build() is sentinel


def test_unavailable_plugin_reports_reason_and_hint():
    plugin = LoadedPlugin(
        name="missing",
        label="缺失插件",
        available=False,
        reason="缺少依赖 numpy",
        install_hint='pip install "issuedoctor[vector]"',
    )
    try:
        plugin.build()
    except PluginUnavailable as exc:
        assert exc.name == "missing"
        assert "numpy" in exc.reason
        assert "issuedoctor[vector]" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected PluginUnavailable")


def test_plugin_map_is_keyed_by_name():
    mapping = plugin_map()
    assert set(mapping) == {plugin.name for plugin in discover_plugins()}
    for name, plugin in mapping.items():
        assert plugin.name == name


def test_summary_is_serialisable():
    import json

    payload = summary()
    json.dumps(payload)
    for item in payload:
        assert {"name", "label", "available", "reason", "install_hint"} <= set(item)


def test_entry_point_group_name_is_stable():
    assert ENTRY_POINT_GROUP == "issuedoctor.plugins"


def test_evaluate_marks_plugin_available_when_no_capability_required():
    from issuedoctor.plugins import _evaluate

    loaded = _evaluate(PluginSpec(name="x", label="X", requires=None, factory=lambda: 1))
    assert loaded.available
    assert loaded.build() == 1


def test_evaluate_reports_missing_capability(monkeypatch):
    from issuedoctor import plugins as plugins_module

    monkeypatch.setattr(
        plugins_module,
        "probe",
        lambda _name: type(
            "S", (), {"available": False, "missing": ("numpy",), "install_hint": "hint"}
        )(),
    )
    loaded = plugins_module._evaluate(
        PluginSpec(name="y", label="Y", requires="vector", factory=lambda: 1)
    )
    assert not loaded.available
    assert "numpy" in loaded.reason
    assert loaded.install_hint == "hint"
