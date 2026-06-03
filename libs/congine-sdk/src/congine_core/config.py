"""Congine SDK configuration plane.

This module defines the immutable runtime configuration used across every
Congine layer.  Configuration is intentionally a plain dataclass with zero
framework dependencies so that it can be imported by any layer (it sits at the
root, shared level of the architecture).

Environment loading is supported via :meth:`CongineConfig.from_env`, which maps
the ``CONGINE_*`` environment variables onto strongly typed fields.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Region(str, Enum):
    """Deployment region for the Congine control plane.

    Inherits from :class:`str` so members compare and serialize ergonomically.
    """

    US = "us"  # Virginia
    EU = "eu"  # Frankfurt (GDPR)
    APAC = "apac"  # Singapore


class FailMode(str, Enum):
    """Behavior on validation failure."""

    STRICT = "strict"  # Fail immediately
    DEGRADE = "degrade"  # Log and continue
    SILENT = "silent"  # Ignore failures


@dataclass
class CongineConfig:
    """Congine SDK configuration.

    Attributes
    ----------
    base_url:
        Base URL of the Congine control plane.
    api_key:
        API key used to authenticate against the control plane.
    project_id:
        Identifier of the calling project.
    tenant_id:
        Identifier of the calling tenant (multi-tenant isolation).
    region:
        Deployment :class:`Region`.
    validation_timeout_ms:
        Hard wall-clock budget (milliseconds) for a single validation run.
    fail_mode:
        How the SDK behaves when validation fails (:class:`FailMode`).
    cache_capacity:
        Maximum number of schemas held in the local cache.
    cache_ttl_seconds:
        Default time-to-live, in seconds, for each cached schema.
    """

    # --- Control plane ---------------------------------------------------- #
    base_url: str
    api_key: Optional[str]
    project_id: Optional[str]
    tenant_id: Optional[str]
    region: Region

    # --- Validation ------------------------------------------------------- #
    validation_timeout_ms: int = 15
    fail_mode: FailMode = FailMode.DEGRADE

    # --- Cache ------------------------------------------------------------ #
    cache_capacity: int = 500
    cache_ttl_seconds: int = 300

    @classmethod
    def from_env(cls) -> "CongineConfig":
        """Load configuration from ``CONGINE_*`` environment variables.

        Returns
        -------
        CongineConfig
            A configuration instance populated from the environment, falling
            back to sensible defaults where variables are unset.
        """
        return cls(
            base_url=os.getenv("CONGINE_BASE_URL", "http://localhost:8080"),
            api_key=os.getenv("CONGINE_API_KEY"),
            project_id=os.getenv("CONGINE_PROJECT_ID"),
            tenant_id=os.getenv("CONGINE_TENANT_ID"),
            region=Region(os.getenv("CONGINE_REGION", "us")),
            validation_timeout_ms=int(os.getenv("CONGINE_TIMEOUT_MS", "15")),
            fail_mode=FailMode(os.getenv("CONGINE_FAIL_MODE", "degrade")),
            cache_capacity=int(os.getenv("CONGINE_CACHE_CAPACITY", "500")),
            cache_ttl_seconds=int(os.getenv("CONGINE_CACHE_TTL", "300")),
        )


__all__ = ["Region", "FailMode", "CongineConfig"]
