"""The two conversation-access test scaffolding helpers.

``_setup`` builds a per-test conversation-reader context (config, request with
stub AuthContext, event store, thread store, run-manager mock) and ``_put``
appends one message event to that store. They live here — a shared, never
collected ``_``-prefixed module — instead of inside
``test_conversation_access.py``, so sibling conversation test files import a
fixture library rather than another collected test module.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from langgraph.store.memory import InMemoryStore

from app.gateway.authz import AuthContext
from deerflow.config.app_config import AppConfig
from deerflow.persistence.thread_meta.memory import MemoryThreadMetaStore
from deerflow.runtime.events.store.memory import MemoryRunEventStore
from deerflow.runtime.runs.manager import EditReplayVisibility


def _setup(*, user_id="alice", permissions=("runs:read",), enabled=True, tool_output=None):
    from app.gateway.conversation_access import prepare_conversation_reader

    config = AppConfig.model_validate(
        {
            "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
            "tools": [{"name": "read_conversation", "group": "conversation", "use": "deerflow.tools.conversation:read_conversation"}] if enabled else [],
            **({"tool_output": tool_output} if tool_output is not None else {}),
        }
    )
    user = SimpleNamespace(id=user_id, system_role="admin")
    request = SimpleNamespace(state=SimpleNamespace(auth=AuthContext(user, list(permissions))), url="https://deerflow.example/api/threads/current/runs")
    events = MemoryRunEventStore()
    threads = MemoryThreadMetaStore(InMemoryStore())
    manager = AsyncMock()
    manager.list_successful_regenerate_sources.return_value = set()
    manager.list_edit_replay_visibility.return_value = EditReplayVisibility()
    ctx = SimpleNamespace(event_store=events, thread_store=threads)

    def prepare(references):
        return prepare_conversation_reader(references, request=request, user_id=user_id, run_context=ctx, run_manager=manager, app_config=config)

    return prepare, events, threads, manager, request


async def _put(events, text, *, role="ai", thread="source", hidden=False, caller="lead_agent", run_id="run-1"):
    return await events.put(
        thread_id=thread,
        run_id=run_id,
        category="message",
        event_type="llm.ai.response" if role == "ai" else "llm.human.input",
        content={"type": role, "id": "message-" + str(len(events._events.get(thread, []))), "content": text, "additional_kwargs": {"hide_from_ui": hidden}},
        metadata={"caller": caller},
    )
