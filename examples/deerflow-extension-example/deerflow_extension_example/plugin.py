"""Deliberately small contribution implementations, one per supported kind.

The example's own behaviour is intentionally trivial — it exists so the
test suite can demonstrate the five-step evidence ladder
(``docs/testing/`` in the DeerFlow repository) against a real extension.

``note`` in the private ``config`` is the configurability showcase, and its
shape is dictated by the host contract: contributed middlewares are wrapped by
``IsolatedMiddleware``, whose wrap hooks are **observational** — the wrapper
pins the original request, so a contribution cannot substitute a rewritten
model request. What a contribution owns on the model-visible surface is its
*tools*: with a note configured, ``ExampleMiddleware`` contributes one
middleware tool whose schema text and result carry the note. One flag, both
faces: the model-visible face (tool schema via ``bind_tools``, tool result in
the message transcript) and the descriptor face
(``release_policy_parameters`` -> ``MiddlewareDescriptor.policy_parameters``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from deerflow_extension_api import (
    AgentBuildContext,
    AgentScope,
    ExtensionData,
    ExtensionRuntimeDeps,
    MiddlewarePlacement,
    Placement,
    SystemModelRequest,
    SystemModelResult,
    SystemOperationKind,
    TaskInfo,
    TaskOutcome,
    task_store_from_runtime,
)
from fastapi import APIRouter, Depends, HTTPException
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import tool as langchain_tool
from langgraph.prebuilt.tool_node import ToolCallRequest


@dataclass
class ExampleStats:
    """Small extension-owned value used in both app and task stores."""

    tool_calls: int = 0
    tasks: dict[str, int] = field(default_factory=dict)
    system_model_calls: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def note_tool_call(self) -> None:
        with self._lock:
            self.tool_calls += 1

    def task_tool_calls(self) -> int:
        with self._lock:
            return self.tool_calls

    def absorb_task(self, tool_calls: int, outcome: TaskOutcome) -> None:
        with self._lock:
            self.tool_calls += tool_calls
            key = outcome.value
            self.tasks[key] = self.tasks.get(key, 0) + 1

    def note_system_call(self, kind: SystemOperationKind, *, failed: bool) -> None:
        with self._lock:
            entry = self.system_model_calls.setdefault(
                kind.value,
                {"calls": 0, "errors": 0},
            )
            entry["calls"] += 1
            if failed:
                entry["errors"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tasks": dict(self.tasks),
                "tool_calls": self.tool_calls,
                "system_model_calls": {kind: dict(counts) for kind, counts in self.system_model_calls.items()},
            }


def _stats(store: ExtensionData) -> ExampleStats:
    return store.get_or_init(ExampleStats, ExampleStats)


class ExampleMiddleware(AgentMiddleware):
    """Counts tool calls into the extension task store (observational wrap).

    Constructed with a ``note``, it additionally owns one middleware tool
    whose schema text and result carry the note — the model-visible surface a
    contributed middleware actually owns. Implement both wrap sides when both
    execution paths must be observed; LangChain treats a sync/async pair as
    one capability and a single-sided wrapper observes only one path.
    """

    def __init__(self, note: str | None = None) -> None:
        super().__init__()
        self._note = note
        self.tools = [self._make_note_tool()] if note is not None else []

    def release_policy_parameters(self) -> dict[str, Any]:
        """Own the descriptor identity: no private-attribute probing fallback."""
        return {"note": self._note}

    def _make_note_tool(self) -> Any:
        note = self._note

        @langchain_tool(description=f"Return the operator-configured example note: {note}")
        def example_note() -> str:
            return note

        return example_note

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        task_store = task_store_from_runtime(getattr(request, "runtime", None))
        task_stats = task_store.get(ExampleStats) if task_store is not None else None
        if task_stats is not None:
            task_stats.note_tool_call()
        return await handler(request)


class ExampleMiddlewareContributor:
    def __init__(self, note: str | None = None) -> None:
        self._note = note

    def contribute_middlewares(
        self,
        app_store: ExtensionData,
        ctx: AgentBuildContext,
    ) -> Sequence[MiddlewarePlacement]:
        return (
            MiddlewarePlacement(
                ExampleMiddleware(note=self._note),
                Placement.TOOL_VISIBLE,
                AgentScope.BOTH,
            ),
        )


class ExampleTaskLifecycle:
    async def on_task_start(
        self,
        app_store: ExtensionData,
        task_store: ExtensionData,
        info: TaskInfo,
    ) -> None:
        task_store.set(ExampleStats())

    async def on_task_stop(
        self,
        app_store: ExtensionData,
        task_store: ExtensionData,
        info: TaskInfo,
        outcome: TaskOutcome,
    ) -> None:
        task_stats = task_store.remove(ExampleStats)
        _stats(app_store).absorb_task(
            task_stats.task_tool_calls() if task_stats is not None else 0,
            outcome,
        )


class ExampleSystemObserver:
    async def on_system_model_call(
        self,
        app_store: ExtensionData,
        task_store: ExtensionData,
        kind: SystemOperationKind,
        request: SystemModelRequest,
        result: SystemModelResult,
    ) -> None:
        _stats(app_store).note_system_call(kind, failed=result.error is not None)


class ExampleService:
    def __init__(self) -> None:
        self._deps: ExtensionRuntimeDeps | None = None

    async def start(self, deps: ExtensionRuntimeDeps) -> None:
        self._deps = deps

    async def stop(self) -> None:
        self._deps = None

    async def require_deps(self) -> ExtensionRuntimeDeps:
        deps = self._deps
        if deps is None or deps.app_store is None:
            raise HTTPException(
                status_code=503,
                detail="extension-example is not running",
            )
        return deps


def build_router(service: ExampleService) -> APIRouter:
    """Build paths during registration, before runtime dependencies exist."""
    router = APIRouter(prefix="/api/extension-example", tags=["extension-example"])

    @router.get("/stats")
    async def read_stats(
        deps: ExtensionRuntimeDeps = Depends(service.require_deps),
    ) -> dict[str, Any]:
        assert deps.app_store is not None
        return {
            "scope_id": deps.app_store.scope_id,
            "session_factory_available": deps.session_factory is not None,
            "host_policy": {
                "max_subagents_per_run": deps.policy.max_subagents_per_run,
            },
            **_stats(deps.app_store).snapshot(),
        }

    return router
