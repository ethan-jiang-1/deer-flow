"""Step 3 — load containment.

DeerFlow extensions are startup-only (changing ``plugins:`` needs a restart),
so this step is not about dispose/HMR. Its invariants are what the host does
when an extension misbehaves:

- ``enabled: false`` must skip an extension without importing it;
- an optional extension that cannot load must fail OPEN with an attributed
  diagnostic, leaving other extensions untouched;
- ``required: true`` must fail CLOSED — that is the operator's explicit
  opt-in to aborting Gateway startup;
- a contributor that explodes at composition time must be isolated to its own
  extension: the other contributions still land, wrapped by the real
  ``IsolatedMiddleware``.
"""

from __future__ import annotations

import pytest
from deerflow.extensions.loader import ExtensionLoadError, ExtensionSpec
from deerflow.extensions.registry import LoadedExtensions
from deerflow.testing import (
    compose_stack,
    extension_process_state,
    load_extensions_for_test,
)
from deerflow_extension_api import AgentScope

GOOD = "deerflow_extension_example:install"
MISSING = "no_such_module_for_tests:install"


def test_disabled_spec_contributes_nothing() -> None:
    with extension_process_state():
        loaded, diagnostics = load_extensions_for_test([ExtensionSpec(use=GOOD, enabled=False)])

    assert not loaded.has_middleware_contributors
    assert not loaded.middleware_contributors
    assert all(diagnostic.level != "error" for diagnostic in diagnostics)


def test_optional_extension_failure_fails_open_with_attribution() -> None:
    with extension_process_state():
        loaded, diagnostics = load_extensions_for_test([ExtensionSpec(use=MISSING)])

    assert not loaded.has_middleware_contributors
    assert diagnostics, "a silent skip would hide the misconfiguration"
    assert any(MISSING in f"{diagnostic.source} {diagnostic.message}" for diagnostic in diagnostics)


def test_required_extension_failure_fails_closed() -> None:
    with extension_process_state(), pytest.raises(ExtensionLoadError):
        load_extensions_for_test([ExtensionSpec(use=MISSING, required=True)])


def test_incompatible_api_marker_is_rejected_by_the_loader() -> None:
    """A present-but-incompatible api marker is rejected and attributed.

    (An *absent* marker is tolerated by the loader today — the marker
    contract is enforced by the ``@extension`` decorator plus this rejection
    for anything that declares one.)
    """
    with extension_process_state():
        loaded, diagnostics = load_extensions_for_test([ExtensionSpec(use="broken_extension:incompatible_marker")])

    assert not loaded.has_middleware_contributors
    assert diagnostics, "the loader must attribute the rejection, not skip silently"
    assert any("9.0.0" in diagnostic.message and "host provides" in diagnostic.message for diagnostic in diagnostics)


def test_failing_install_is_rolled_back_and_attributed() -> None:
    with extension_process_state():
        loaded, diagnostics = load_extensions_for_test([ExtensionSpec(use="broken_extension:raising_install")])

    assert not loaded.has_middleware_contributors
    assert any(diagnostic.source == "broken_extension:raising_install" and "install() failed" in diagnostic.message for diagnostic in diagnostics)


def _explode_plus_good() -> list[ExtensionSpec]:
    return [
        ExtensionSpec(use="broken_extension:exploding_contributor"),
        ExtensionSpec(use=GOOD),
    ]


def test_contributor_explosion_is_isolated_and_good_contributions_still_land() -> None:
    from deerflow.extensions import get_runtime_diagnostics

    with extension_process_state():
        loaded, _ = load_extensions_for_test(_explode_plus_good())
        stack = compose_stack(loaded, scope=AgentScope.LEAD)

        inners = [getattr(middleware, "inner", middleware) for middleware in stack]
        assert any(type(middleware).__name__ == "ExampleMiddleware" for middleware in inners), "one extension's failure must not evict another extension's contribution"

        assert any(diagnostic.source == "broken_extension:exploding_contributor" and "contributor exploded" in diagnostic.message for diagnostic in get_runtime_diagnostics())


def test_loaded_extensions_shape_is_immutable_and_attributed() -> None:
    with extension_process_state():
        loaded, _ = load_extensions_for_test([ExtensionSpec(use=GOOD)])

    assert isinstance(loaded, LoadedExtensions)
    sources = {source for source, _contributor in loaded.middleware_contributors}
    assert sources == {GOOD}
