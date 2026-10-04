"""A compact, standalone DeerFlow extension exercising every contribution kind."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow_extension_api import ExtensionInstall, ExtensionRegistry, extension

from deerflow_extension_example.plugin import (
    ExampleMiddlewareContributor,
    ExampleService,
    ExampleSystemObserver,
    ExampleTaskLifecycle,
    build_router,
)

__all__ = ["install"]


@extension(api="0.2.0", name="example")
def install(registry: ExtensionRegistry, config: Mapping[str, Any]) -> None:
    """Register one example of each supported contribution kind.

    Private config (the per-plugin ``config:`` block of the managed
    ``plugins:`` record): ``enabled: false`` skips registration entirely;
    ``note: <str>`` additionally gives the contributed middleware one
    note-carrying tool — the config surface the test suite proves on both
    faces (model-visible tool schema/result, assembly descriptor).
    """
    if config.get("enabled", True) is False:
        return

    note_raw = config.get("note")
    note = str(note_raw) if note_raw else None

    service = ExampleService()
    registry.middlewares(ExampleMiddlewareContributor(note=note))
    registry.task_lifecycle(ExampleTaskLifecycle())
    registry.system_model_observer(ExampleSystemObserver())
    registry.service(service)
    registry.routers((build_router(service),))


_entry_point: ExtensionInstall = install
