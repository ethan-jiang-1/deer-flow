"""Step 5 — the model-visible transcript, pinned keylessly.

The full DeerFlow lane for this step is record/replay:
``backend/scripts/record_gateway.py`` captures a real scenario into
``backend/tests/fixtures/replay/*.json`` and ``backend/tests/replay_provider.py``
replays it hash-by-input without an API key. An extension repo can pin its own
keyless slice with the same discipline: assert the exact transcript the model
receives for a scripted scenario, so any change to what the model is told
fails the diff until the expectation is consciously refreshed.

This file is that pin for the example's ``note`` scenario: one scripted tool
call, the configured note coming back as the tool result, the loop closing.
If you change what the model sees (tool naming, result shape, message flow),
this test fails — that is the point. Refresh it in the same PR as the change.
"""

from __future__ import annotations

import asyncio

from deerflow.extensions.loader import ExtensionSpec
from deerflow.testing import (
    ScriptedModel,
    build_test_agent,
    extension_process_state,
    load_extensions_for_test,
    tool_call_then_final,
)
from langchain_core.messages import HumanMessage, ToolMessage


def test_model_receives_a_stable_transcript_for_the_scripted_scenario() -> None:
    with extension_process_state():
        loaded, diagnostics = load_extensions_for_test([ExtensionSpec(use="deerflow_extension_example:install", config={"note": "example-note-active"})])
        assert diagnostics == []

        model = ScriptedModel(tool_call_then_final("example_note", {}, final_text="done"))
        agent = build_test_agent(loaded, model)
        state = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content="hello")]}))

    assert len(model.requests) == 2, f"expected a two-call transcript, saw {len(model.requests)}"

    first = [(type(message).__name__, str(message.content)) for message in model.requests[0]]
    assert first == [("HumanMessage", "hello")]

    second = model.requests[1]
    assert isinstance(second[-1], ToolMessage)
    assert second[-1].content == "example-note-active"

    # The scripted reply lands in the graph state as the final message.
    assert state["messages"][-1].content == "done"
