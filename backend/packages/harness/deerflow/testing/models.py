"""The scripted model — the one mock extension tests are allowed to lean on.

Everything downstream of the model (loader, registry, isolation wrapper,
composition, the agent graph itself) is real shipping code; only the model is
a script. The scripted model also records every request it receives and every
``bind_tools`` payload it is given, so tests can assert on the *model-visible
face* (system prompt injections, message shape, exposed tool schemas) instead
of probing agent internals.

What this mock cannot prove (say so in the test when it matters): it does not
exercise a real provider, streaming tokenisation, retries, or rate limits.
Pair keyless scripted tests with the live lane (``make test-live`` /
``DEER_FLOW_RUN_LIVE_TESTS=1``) when the model dependency itself is the
behaviour under test.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable
from pydantic import Field


class ScriptedModel(FakeMessagesListChatModel):
    """Fake chat model with a no-op ``bind_tools`` and full request recording.

    ``langchain.agents.create_agent`` calls ``model.bind_tools(...)`` to expose
    tool schemas to the model; the upstream fake raises ``NotImplementedError``
    there. This subclass records the payload and returns ``self`` — the script
    produces deterministic tool-call output, so no schema handling is needed.

    Responses **cycle** (upstream behaviour): once the script is exhausted, the
    last response repeats, so a graph that calls the model more often than
    scripted still terminates instead of raising.

    Recorded state (test-visible, not functional):

    - ``requests`` — every message list the graph sent to the model, in call
      order. This is the model-visible face.
    - ``bound_tools`` — every ``bind_tools`` payload, in call order. Tool
      schemas reach the model through this call, so they are part of the same
      face.
    """

    requests: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[Any] = Field(default_factory=list)

    def __init__(self, responses: list[BaseMessage]) -> None:
        """Script the responses (positional, like the upstream fake).

        Responses **cycle**: once exhausted, the last response repeats.
        """
        super().__init__(responses=responses)

    def bind_tools(  # type: ignore[override]
        self,
        tools: Any,
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Runnable:
        self.bound_tools.append(tools)
        return self

    def _generate(  # type: ignore[override]
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.requests.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def tool_call_message(
    tool_name: str,
    tool_args: dict[str, Any],
    *,
    call_id: str = "call_scripted_1",
    content: str = "",
) -> AIMessage:
    """One scripted turn that emits a single tool call."""
    return AIMessage(
        content=content,
        tool_calls=[
            {
                "name": tool_name,
                "args": dict(tool_args),
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def final_message(text: str = "done") -> AIMessage:
    """One scripted turn that terminates the agent loop."""
    return AIMessage(content=text)


def tool_call_then_final(
    tool_name: str,
    tool_args: dict[str, Any],
    *,
    final_text: str = "done",
    call_id: str = "call_scripted_1",
) -> list[BaseMessage]:
    """Two-turn script: emit one tool call, then finish with final text."""
    return [
        tool_call_message(tool_name, tool_args, call_id=call_id),
        final_message(final_text),
    ]
