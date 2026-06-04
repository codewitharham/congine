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

from congine_core.exceptions import CongineConfigurationError


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


@dataclass(frozen=True)
class CongineConfig:
    """Congine SDK configuration.

    The dataclass is ``frozen=True``: once assembled at bootstrap the instance
    is immutable and threaded read-only through every layer. Any attempt to
    mutate a field after construction raises
    :class:`dataclasses.FrozenInstanceError`.

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
    sync_enabled:
        When ``True``, :meth:`ServiceContainer.bootstrap` starts a background
        worker that periodically re-syncs contracts. Off by default.
    sync_interval_seconds:
        Seconds between background contract syncs when ``sync_enabled``.
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

    # --- Background sync -------------------------------------------------- #
    sync_enabled: bool = False
    sync_interval_seconds: int = 300

    # --- Semantic validation & drift ------------------------------------- #
    semantic_validation_enabled: bool = False
    drift_threshold: float = 0.1
    drift_sample_limit: int = 500

    # --- Validation pool (bounded, load-shedding) ------------------------ #
    validation_max_workers: int = 10
    validation_max_pending: int = 10

    # --- Snapshot / security / observability ----------------------------- #
    snapshot_dir: Optional[str] = None
    require_https: bool = False
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "CongineConfig":
        """Load configuration from ``CONGINE_*`` environment variables.

        Returns
        -------
        CongineConfig
            A configuration instance populated from the environment, falling
            back to sensible defaults where variables are unset.

        Raises
        ------
        CongineConfigurationError
            If an environment value cannot be parsed into its target type
            (e.g. an unknown region/fail-mode, or a non-integer numeric).
        """
        try:
            region = Region(os.getenv("CONGINE_REGION", "us"))
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid CONGINE_REGION: {os.getenv('CONGINE_REGION')!r}"
            ) from exc
        try:
            fail_mode = FailMode(os.getenv("CONGINE_FAIL_MODE", "degrade"))
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid CONGINE_FAIL_MODE: {os.getenv('CONGINE_FAIL_MODE')!r}"
            ) from exc

        config = cls(
            base_url=os.getenv("CONGINE_BASE_URL", "http://localhost:8080"),
            api_key=os.getenv("CONGINE_API_KEY"),
            project_id=os.getenv("CONGINE_PROJECT_ID"),
            tenant_id=os.getenv("CONGINE_TENANT_ID"),
            region=region,
            validation_timeout_ms=cls._env_int("CONGINE_TIMEOUT_MS", 15),
            fail_mode=fail_mode,
            cache_capacity=cls._env_int("CONGINE_CACHE_CAPACITY", 500),
            cache_ttl_seconds=cls._env_int("CONGINE_CACHE_TTL", 300),
            sync_enabled=cls._env_bool("CONGINE_SYNC_ENABLED", False),
            sync_interval_seconds=cls._env_int("CONGINE_SYNC_INTERVAL", 300),
            semantic_validation_enabled=cls._env_bool(
                "CONGINE_SEMANTIC_VALIDATION", False
            ),
            drift_threshold=cls._env_float("CONGINE_DRIFT_THRESHOLD", 0.1),
            drift_sample_limit=cls._env_int("CONGINE_DRIFT_SAMPLE_LIMIT", 500),
            validation_max_workers=cls._env_int("CONGINE_VALIDATION_WORKERS", 10),
            validation_max_pending=cls._env_int("CONGINE_VALIDATION_PENDING", 10),
            snapshot_dir=os.getenv("CONGINE_SNAPSHOT_DIR"),
            require_https=cls._env_bool("CONGINE_REQUIRE_HTTPS", False),
            log_level=os.getenv("CONGINE_LOG_LEVEL", "INFO").upper(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate completeness and security policy (audit H4).

        For a non-local control plane, the tenant-isolation credentials must be
        present, and (when ``require_https``) the URL must be HTTPS. Raises
        :class:`CongineConfigurationError` on violation — no silent boot.
        """
        if self.is_local_base_url():
            return
        missing = [
            name
            for name, value in (
                ("api_key", self.api_key),
                ("project_id", self.project_id),
                ("tenant_id", self.tenant_id),
            )
            if not value
        ]
        if missing:
            raise CongineConfigurationError(
                f"Incomplete configuration for non-local base_url: missing {missing}"
            )
        if self.require_https and not self.base_url.lower().startswith("https://"):
            raise CongineConfigurationError(
                "base_url must use https for a non-local control plane "
                "(set CONGINE_REQUIRE_HTTPS=false to override)"
            )

    def is_local_base_url(self) -> bool:
        """Return ``True`` if the control plane is local (loopback)."""
        url = (self.base_url or "").lower()
        return (
            "localhost" in url
            or "127.0.0.1" in url
            or "::1" in url
            or url.startswith("http://0.0.0.0")
        )

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        """Parse a boolean environment variable *name*, defaulting if unset.

        Truthy values (case-insensitive): ``1``, ``true``, ``yes``, ``on``.
        """
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        """Parse integer environment variable *name*, defaulting if unset.

        Raises
        ------
        CongineConfigurationError
            If the variable is set but not a valid integer.
        """
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid integer for {name}: {raw!r}"
            ) from exc

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        """Parse a float environment variable *name*, defaulting if unset.

        Raises
        ------
        CongineConfigurationError
            If the variable is set but not a valid float.
        """
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid float for {name}: {raw!r}"
            ) from exc


__all__ = ["Region", "FailMode", "CongineConfig"]
