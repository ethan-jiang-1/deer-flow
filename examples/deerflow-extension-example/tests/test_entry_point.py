"""Step 1 — the entry-point contract guard, at both layers.

The packaging layer proves the distribution exposes exactly one entry point in
the ``deerflow.extensions`` group with a valid api marker. The loader layer
(the real ``load_extensions`` over the shipped entry point) proves the marker
is accepted and every promised contribution kind actually registers — the
loader, not this file, is the authority on marker compatibility.
"""

from importlib.metadata import distribution


def test_installed_distribution_exposes_deerflow_extension_entry_point() -> None:
    entry_points = [entry_point for entry_point in distribution("deerflow-extension-example").entry_points if entry_point.group == "deerflow.extensions"]

    assert [(entry_point.name, entry_point.value) for entry_point in entry_points] == [("example", "deerflow_extension_example:install")]

    install = entry_points[0].load()
    assert install.__deerflow_api__ == "0.2.0"
    assert install.__deerflow_name__ == "example"


def test_real_loader_registers_every_contribution_kind_from_the_entry_point() -> None:
    from deerflow.extensions.loader import ExtensionSpec
    from deerflow.testing import extension_process_state, load_extensions_for_test

    with extension_process_state():
        loaded, diagnostics = load_extensions_for_test([ExtensionSpec(use="deerflow_extension_example:install")])

    assert diagnostics == []
    assert loaded.has_middleware_contributors
    assert loaded.has_task_lifecycle
    assert loaded.has_system_model_observers
    assert loaded.services and loaded.routers
