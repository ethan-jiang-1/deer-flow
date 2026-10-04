"""Step 4 — REAL composition with both faces of one config flag.

A registry assembled by hand only to satisfy a test proves nothing about what
the Gateway would load. Boot the real loader over a real ``ExtensionSpec``
(what a managed ``plugins:`` record holds), compose through the real
composition point, and drive the real agent graph — then assert the configured
flag on BOTH faces:

- the model-visible face: the note reaches the tool schema the model receives
  (recorded by the scripted model's ``bind_tools``) and the tool result the
  model reads back in the message transcript. Contributed middlewares are
  observational through ``IsolatedMiddleware`` — the wrapper pins the original
  request — so middleware-owned tools ARE the model-visible surface a
  contribution owns;
- the descriptor face: the same note is what assembly observers see
  (``release_policy_parameters`` -> ``MiddlewareDescriptor.policy_parameters``,
  which feeds the assembly fingerprint), attributed to the contributing
  extension.

``DEFAULT_*`` constants and unit-test hooks are not configurability evidence:
only a flag that demonstrably moves both faces through the real loader is.
"""

from __future__ import annotations

import asyncio
import json

from deerflow.extensions.loader import ExtensionSpec
from deerflow.testing import (
    ScriptedModel,
    build_test_agent,
    compose_stack,
    describe_middleware,
    extension_process_state,
    final_message,
    load_extensions_for_test,
    tool_call_then_final,
)
from deerflow_extension_api import AgentScope
from langchain_core.messages import HumanMessage, ToolMessage

GOOD = "deerflow_extension_example:install"


def _boot(config: dict) -> tuple:
    loaded, diagnostics = load_extensions_for_test([ExtensionSpec(use=GOOD, config=config)])
    assert diagnostics == []
    return loaded


def _bound_payload_texts(model: ScriptedModel) -> list[str]:
    """Render each recorded ``bind_tools`` payload to searchable text.

    LangChain may hand the model BaseTool objects or provider-shaped schemas;
    the assertion is about what the model was given, in whatever shape that is.
    """
    texts = []
    for payload in model.bound_tools:
        if isinstance(payload, str):
            texts.append(payload)
            continue
        try:
            texts.append(json.dumps(payload, default=str))
        except TypeError:
            texts.append(str(payload))
    return texts


def test_note_config_flows_to_both_faces() -> None:
    with extension_process_state():
        loaded = _boot({"note": "example-note-active"})

        model = ScriptedModel(tool_call_then_final("example_note", {}, final_text="done"))
        agent = build_test_agent(loaded, model)
        state = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content="hello")]}))

        # Face 1 — model-visible, before the call: the tool schema carries the note.
        assert model.bound_tools, "the graph never bound tools"
        assert any("example_note" in text and "example-note-active" in text for text in _bound_payload_texts(model))

        # Face 1 — model-visible, after the call: the model reads the result.
        tool_messages = [message for message in state["messages"] if isinstance(message, ToolMessage)]
        assert [message.content for message in tool_messages] == ["example-note-active"]
        assert model.requests[1][-1].content == "example-note-active", "the tool result must reach the next model request"

        # ...and the conversation still completes through the real graph.
        assert state["messages"][-1].content == "done"

        # Face 2 — descriptor: the same flag is visible to assembly observers,
        # attributed to the contributing extension.
        stack = compose_stack(loaded, scope=AgentScope.LEAD)
        described = [describe_middleware(middleware) for middleware in stack]
        example_descriptors = [entry for entry in described if entry.name == "ExampleMiddleware"]
        assert example_descriptors, "the configured middleware must reach the composed stack"
        assert example_descriptors[0].policy_parameters == {"note": "example-note-active"}
        assert example_descriptors[0].extension == GOOD


def test_without_config_the_note_is_absent_from_every_face() -> None:
    with extension_process_state():
        loaded = _boot({})

        model = ScriptedModel([final_message("done")])
        agent = build_test_agent(loaded, model)
        state = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content="hello")]}))

        assert all("example_note" not in text for text in _bound_payload_texts(model))
        assert not [message for message in state["messages"] if isinstance(message, ToolMessage)]

        stack = compose_stack(loaded, scope=AgentScope.LEAD)
        described = [describe_middleware(middleware) for middleware in stack]
        example_descriptors = [entry for entry in described if entry.name == "ExampleMiddleware"]
        assert example_descriptors[0].policy_parameters == {"note": None}


def test_disabled_config_still_boots_the_rest_of_the_extension() -> None:
    """``enabled: false`` is a full skip; config alone cannot half-disable."""
    with extension_process_state():
        loaded, diagnostics = load_extensions_for_test([ExtensionSpec(use=GOOD, config={"enabled": False, "note": "ignored"})])
        assert diagnostics == []
        assert not loaded.has_middleware_contributors
