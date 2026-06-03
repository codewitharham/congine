"""Layer 5: Framework entry points (adapters).

Depends on every layer below; this is the top of the dependency graph.
"""

from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.adapters.guard import congine_guard

__all__ = ["ServiceContainer", "congine_guard"]
