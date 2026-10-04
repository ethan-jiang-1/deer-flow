"""Real-entry-path composition helpers for extension tests.

Everything here drives DeerFlow's shipping entry points — the real loader over
real ``ExtensionSpec`` objects, the real composition point
(``deerflow.extensions.stack.compose_with_extensions``), the real
``create_agent`` graph builder — so a passing test is evidence about the
assembled system rather than about a hand-wired replica of it. A registry
assembled by hand only to satisfy a test proves nothing about whether the
Gateway would load and compose the same contributions.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any

from deerflow_extension_api import AgentBuildContext, AgentScope
from langchain.agents import create_agent
from langchain_core.runnables import Runnable

from deerflow.extensions import reset_loaded_extensions, reset_runtime_diagnostics
from deerflow.extensions.loader import Diagnostic, ExtensionSpec, load_extensions
from deerflow.extensions.registry import LoadedExtensions
from deerflow.extensions.stack import compose_with_extensions


@contextmanager
def extension_process_state():
    """Isolate the process-global extension state for one test.

    The loaded-extension singleton and the runtime diagnostics list are
    process-global; the Gateway owns them at startup. Tests that boot
    extensions or compose stacks must reset both sides, or a diagnostics
    assertion in one test can be satisfied by a warning leaked from an earlier
    one. Use as a context manager or inside a fixture.
    """
    reset_loaded_extensions()
    reset_runtime_diagnostics()
    try:
        yield
    finally:
        reset_runtime_diagnostics()
        reset_loaded_extensions()


def load_extensions_for_test(
    specs: Sequence[ExtensionSpec],
) -> tuple[LoadedExtensions, list[Diagnostic]]:
    """Run the real loader exactly as Gateway startup would.

    Returns the loaded registry and its load diagnostics. Assertions on both
    belong in the test, because which failures are acceptable (fail-open
    diagnostics for optional extensions) versus fatal (``required: true``
    aborting startup) is part of the behaviour under test.
    """
    return load_extensions(list(specs))


def compose_stack(
    extensions: LoadedExtensions,
    *,
    scope: AgentScope = AgentScope.LEAD,
    core_middlewares: Sequence[object] = (),
    build_context: AgentBuildContext | None = None,
) -> list[object]:
    """Compose extension contributions through the real composition point.

    With an empty ``core_middlewares`` the host's semantic-placement anchors
    are absent, so every contribution degrades to the documented fallback
    (outermost/innermost, with a warning diagnostic). That is acceptable for
    extension-level evidence; pass the real core stack when placement relative
    to specific host middlewares is itself the assertion.

    Composition failures are recorded to the process-global runtime
    diagnostics list — run inside :func:`extension_process_state`.
    """
    context = build_context or AgentBuildContext(scope=scope)
    return compose_with_extensions(list(core_middlewares), scope, context, extensions)


def build_test_agent(
    extensions: LoadedExtensions,
    model: Any,
    *,
    scope: AgentScope = AgentScope.LEAD,
    core_middlewares: Sequence[object] = (),
    build_context: AgentBuildContext | None = None,
) -> Runnable:
    """Build a real agent graph around the scripted model.

    Contributions enter through the real composition point and are wrapped by
    the real isolation layer; the only stand-in is the model itself. Drive the
    result with ``ainvoke``/``astream`` and assert on the returned state, the
    scripted model's recorded requests, or the process diagnostics — not by
    probing graph internals.
    """
    stack = compose_stack(
        extensions,
        scope=scope,
        core_middlewares=core_middlewares,
        build_context=build_context,
    )
    return create_agent(model, middleware=stack)


__all__ = [
    "build_test_agent",
    "compose_stack",
    "extension_process_state",
    "load_extensions_for_test",
]
