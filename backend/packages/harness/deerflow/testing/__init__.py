"""``deerflow.testing`` — the extension/agent author's test kit.

Test-only code that ships with the harness so downstream DeerFlow-based agent
repos import these helpers instead of copying fakes. It must never import
``app.*`` (the harness/app boundary applies) and stays framework-light: every
helper drives the real entry points (loader, composition, agent builder)
around a single scripted-model stand-in.

The five-step evidence ladder this kit implements lives in ``docs/testing/``
in the DeerFlow repository:

1. entry-point contract guard (real loader over the shipped entry point);
2. behaviour spec from the real registered entry (only the model is a
   stand-in);
3. load containment (fail-open diagnostics, ``required`` fail-closed,
   ``enabled: false`` skips, contributor-failure isolation);
4. REAL composition with both faces of one config flag (model-visible request
   and assembly descriptor);
5. model-visible transcript, pinned keylessly (full lane: recorded replay).
"""

from deerflow.agents.assembly_descriptor import describe_middleware
from deerflow.testing.extensions import (
    build_test_agent,
    compose_stack,
    extension_process_state,
    load_extensions_for_test,
)
from deerflow.testing.models import (
    ScriptedModel,
    final_message,
    tool_call_message,
    tool_call_then_final,
)

__all__ = [
    "ScriptedModel",
    "build_test_agent",
    "compose_stack",
    "describe_middleware",
    "extension_process_state",
    "final_message",
    "load_extensions_for_test",
    "tool_call_message",
    "tool_call_then_final",
]
