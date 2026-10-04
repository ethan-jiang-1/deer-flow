"""Deliberately broken extension fixtures for load-containment tests.

Not registered by anything: the loader imports these by module path
(``use="broken_extension:..."``) exactly as it would a configured plugin.
The loader tolerates an *absent* api marker but rejects a present-and-
incompatible one, and rolls back a failing ``install()`` — each fixture
exercises one containment branch.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from deerflow_extension_api import ExtensionRegistry, extension


class ExplodingContributor:
    """Fails at composition time, not at install time."""

    def contribute_middlewares(self, app_store: Any, ctx: Any) -> Any:
        raise ValueError("contributor exploded")


@extension(api="9.0.0", name="broken-incompatible")
def incompatible_marker(registry: ExtensionRegistry, config: Mapping[str, Any]) -> None:
    """Declares an extension-api the host does not provide; must be rejected."""
    registry.middlewares(object())


@extension(api="0.2.0", name="broken-exploding-install")
def raising_install(registry: ExtensionRegistry, config: Mapping[str, Any]) -> None:
    """Explodes inside install(); the loader must roll back and attribute."""
    raise ValueError("install exploded")


@extension(api="0.2.0", name="broken-exploding")
def exploding_contributor(registry: ExtensionRegistry, config: Mapping[str, Any]) -> None:
    """Registers one contributor that explodes when the stack is composed."""
    registry.middlewares(ExplodingContributor())
