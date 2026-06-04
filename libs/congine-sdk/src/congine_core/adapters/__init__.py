"""Layer 5: Framework entry points (adapters).

Depends on every layer below; this is the top of the dependency graph.

The optional LangChain handler is exposed lazily via ``__getattr__`` so that
``from congine_core.adapters import CongineCallbackHandler`` works without
eagerly importing ``langchain-core`` for users who never touch it.
"""

from typing import Any

from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.adapters.guard import congine_guard

__all__ = ["ServiceContainer", "congine_guard", "CongineCallbackHandler"]


def __getattr__(name: str) -> Any:
    """Lazily resolve the optional LangChain handler on first access."""
    if name == "CongineCallbackHandler":
        from congine_core.adapters.langchain_handler import (
            CongineCallbackHandler,
        )

        return CongineCallbackHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
