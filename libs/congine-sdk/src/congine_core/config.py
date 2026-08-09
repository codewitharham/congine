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
from typing import FrozenSet, Optional
from urllib.parse import urlparse

from congine_core.exceptions import CongineConfigurationError
from congine_core.security_limits import (
    DEFAULT_MAX_CONTRACT_FILE_BYTES,
    DEFAULT_MAX_CONTRACT_FILES,
    DEFAULT_MAX_HTTP_RESPONSE_BYTES,
    DEFAULT_MAX_PAYLOAD_BYTES,
    DEFAULT_MAX_SCHEMA_BYTES,
    DEFAULT_MAX_STREAM_BUFFER_CHARS,
    DEFAULT_SEMANTIC_MAX_BREACHES,
)

# Exact loopback hostnames exempt from HTTPS/credential policy (FIX-01).
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

#: Control-plane URL per region (audit Q1). ``region`` used to be a validated,
#: documented, *unread* field — a user setting ``CONGINE_REGION=eu`` for data
#: residency got no routing change and no warning. It now selects the default
#: control plane.
#:
#: Applied **only** when ``CONGINE_REGION`` is set explicitly and
#: ``CONGINE_BASE_URL`` is not, so local development (which sets neither) keeps
#: the loopback default and an explicit ``base_url`` always wins.
#:
#: .. important:: These hostnames are the single place regional endpoints are
#:    declared. Confirm them against the deployed control plane before relying
#:    on region-based routing in production.
_REGION_BASE_URLS: "dict[str, str]" = {
    "us": "https://api.us.congine.dev",
    "eu": "https://api.eu.congine.dev",
    "apac": "https://api.apac.congine.dev",
}

#: Default control plane when neither ``CONGINE_BASE_URL`` nor ``CONGINE_REGION``
#: is set — i.e. local development.
_DEFAULT_LOCAL_BASE_URL = "http://localhost:8080"


class Region(str, Enum):
    """Deployment region for the Congine control plane.

    Selects the default ``base_url`` via :data:`_REGION_BASE_URLS` when
    ``CONGINE_BASE_URL`` is not set (audit Q1). An explicit ``base_url`` always
    takes precedence, so setting a region never overrides a deliberate endpoint.

    Inherits from :class:`str` so members compare and serialize ergonomically.
    """

    US = "us"  # Virginia
    EU = "eu"  # Frankfurt (GDPR)
    APAC = "apac"  # Singapore

    @property
    def default_base_url(self) -> str:
        """Control-plane URL for this region."""
        return _REGION_BASE_URLS[self.value]


class FailMode(str, Enum):
    """Behavior on validation failure."""

    STRICT = "strict"  # Fail immediately
    DEGRADE = "degrade"  # Log and continue
    SILENT = "silent"  # Ignore failures


class DeploymentMode(str, Enum):
    """Process deployment topology for container lifecycle policy."""

    SINGLE_TENANT = "single_tenant"
    MULTI_TENANT = "multi_tenant"


@dataclass(frozen=True)
class CongineConfig:
    """Congine SDK configuration.

    The dataclass is ``frozen=True``: once assembled at bootstrap the instance
    is immutable and threaded read-only through every layer.
    """

    # --- Control plane ---------------------------------------------------- #
    base_url: str
    api_key: Optional[str]
    project_id: Optional[str]
    tenant_id: Optional[str]
    region: Region

    # --- Validation ------------------------------------------------------- #
    validation_timeout_ms: int = 100
    fail_mode: FailMode = FailMode.DEGRADE

    # --- Cache ------------------------------------------------------------ #
    cache_capacity: int = 500
    cache_ttl_seconds: int = 300
    cache_sweep_interval_seconds: float = 30.0

    # --- Background sync -------------------------------------------------- #
    sync_enabled: bool = False
    sync_interval_seconds: int = 300

    # --- Semantic validation & drift ------------------------------------- #
    semantic_validation_enabled: bool = False
    semantic_max_breaches: int = DEFAULT_SEMANTIC_MAX_BREACHES
    semantic_format_checking: bool = False
    drift_threshold: float = 0.1
    drift_sample_limit: int = 500
    # JSON Schema dialect for the semantic validator. Typed as a plain string to
    # keep L0 free of the heavy ``jsonschema`` import; L4 maps it to a class.
    jsonschema_draft: str = "draft202012"

    # --- Validation pool (bounded, load-shedding) ------------------------ #
    validation_max_workers: int = 10
    validation_max_pending: int = 10

    # --- Contract source (local-first / GitOps) -------------------------- #
    contract_source: str = "http"
    contracts_dir: Optional[str] = None
    # Explicit standalone / offline-first switch: when set, the container binds a
    # FileContractRepository to this directory and allocates NO background sync
    # daemon (the boot prime reads the directory once).
    local_contracts_dir: Optional[str] = None

    # --- Telemetry pipeline (event bus tuning) --------------------------- #
    # telemetry_enabled=False selects a NoOpEventBus: no drain thread, no I/O.
    telemetry_enabled: bool = True
    telemetry_queue_size: int = 10_000
    telemetry_batch_size: int = 100
    telemetry_max_retries: int = 4
    telemetry_backoff_base: float = 0.5
    telemetry_backoff_max: float = 8.0
    # Shared control-plane HTTP timeout (telemetry ship client + gateway calls).
    control_plane_http_timeout_seconds: float = 10.0

    # --- Snapshot / security / observability ----------------------------- #
    snapshot_dir: Optional[str] = None
    # Cross-process snapshot-write lock wait (portalocker). Lower (e.g. 1.0) for
    # aggressive fail-fast on local NVMe; raise (e.g. 30.0) to ride out heavy
    # read/write contention on a slow shared cloud mount before skipping the
    # best-effort write.
    snapshot_lock_timeout_seconds: float = 10.0
    require_https: bool = True
    allow_cleartext: bool = False
    log_level: str = "INFO"
    log_safe_fields: Optional[FrozenSet[str]] = None
    log_redaction_enabled: bool = True

    # --- Circuit breaker (control-plane boundary protection) ------------- #
    breaker_failure_threshold: int = 5
    breaker_cooldown_seconds: float = 30.0

    # --- Multi-tenant deployment (FIX-05) -------------------------------- #
    deployment_mode: DeploymentMode = DeploymentMode.SINGLE_TENANT

    # --- Input bounds (FIX-06) ------------------------------------------- #
    max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES
    # Caps a *cached schema* on the validation hot path. Distinct from
    # max_contract_file_bytes, which caps a *file read* at load (audit Q11).
    max_schema_bytes: int = DEFAULT_MAX_SCHEMA_BYTES
    max_contract_files: int = DEFAULT_MAX_CONTRACT_FILES
    max_contract_file_bytes: int = DEFAULT_MAX_CONTRACT_FILE_BYTES
    max_stream_buffer_chars: int = DEFAULT_MAX_STREAM_BUFFER_CHARS
    max_http_response_bytes: int = DEFAULT_MAX_HTTP_RESPONSE_BYTES

    # --- Container lifecycle (FIX-14) ------------------------------------ #
    start_background_services: bool = True

    @staticmethod
    def deployment_mode_from_env() -> DeploymentMode:
        """Read **only** ``CONGINE_DEPLOYMENT_MODE`` from the environment.

        Split out of :meth:`from_env` so a caller that needs just the topology —
        notably :meth:`ServiceContainer.get_default`, which must refuse to serve
        a shared singleton in ``multi_tenant`` mode — can check it without
        parsing and validating all ~47 fields on every call (audit Q10).
        """
        raw = os.getenv("CONGINE_DEPLOYMENT_MODE", "single_tenant")
        try:
            return DeploymentMode(raw)
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid CONGINE_DEPLOYMENT_MODE: {raw!r}"
            ) from exc

    @staticmethod
    def base_url_from_env(region: Region) -> str:
        """Resolve the control-plane URL for the current environment (audit Q1).

        Precedence: an explicit ``CONGINE_BASE_URL`` always wins; otherwise an
        explicitly-set ``CONGINE_REGION`` selects its regional endpoint;
        otherwise the loopback default, so local development is unaffected.
        """
        explicit = os.getenv("CONGINE_BASE_URL")
        if explicit:
            return explicit
        if os.getenv("CONGINE_REGION"):
            return region.default_base_url
        return _DEFAULT_LOCAL_BASE_URL

    @classmethod
    def from_env(cls) -> "CongineConfig":
        """Load configuration from ``CONGINE_*`` environment variables."""
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
        deployment_mode = cls.deployment_mode_from_env()

        config = cls(
            base_url=cls.base_url_from_env(region),
            api_key=os.getenv("CONGINE_API_KEY"),
            project_id=os.getenv("CONGINE_PROJECT_ID"),
            tenant_id=os.getenv("CONGINE_TENANT_ID"),
            region=region,
            validation_timeout_ms=cls._env_int("CONGINE_TIMEOUT_MS", 100),
            fail_mode=fail_mode,
            cache_capacity=cls._env_int("CONGINE_CACHE_CAPACITY", 500),
            cache_ttl_seconds=cls._env_int("CONGINE_CACHE_TTL", 300),
            sync_enabled=cls._env_bool("CONGINE_SYNC_ENABLED", False),
            sync_interval_seconds=cls._env_int("CONGINE_SYNC_INTERVAL", 300),
            semantic_validation_enabled=cls._env_bool(
                "CONGINE_SEMANTIC_VALIDATION", False
            ),
            semantic_max_breaches=cls._env_int(
                "CONGINE_SEMANTIC_MAX_BREACHES", DEFAULT_SEMANTIC_MAX_BREACHES
            ),
            semantic_format_checking=cls._env_bool(
                "CONGINE_SEMANTIC_FORMAT_CHECKING", False
            ),
            drift_threshold=cls._env_float("CONGINE_DRIFT_THRESHOLD", 0.1),
            drift_sample_limit=cls._env_int("CONGINE_DRIFT_SAMPLE_LIMIT", 500),
            validation_max_workers=cls._env_int("CONGINE_VALIDATION_WORKERS", 10),
            validation_max_pending=cls._env_int("CONGINE_VALIDATION_PENDING", 10),
            contract_source=os.getenv("CONGINE_CONTRACT_SOURCE", "http").lower(),
            contracts_dir=os.getenv("CONGINE_CONTRACTS_DIR"),
            local_contracts_dir=os.getenv("CONGINE_LOCAL_CONTRACTS_DIR"),
            cache_sweep_interval_seconds=cls._env_float(
                "CONGINE_CACHE_SWEEP_INTERVAL_SECONDS", 30.0
            ),
            jsonschema_draft=os.getenv("CONGINE_JSONSCHEMA_DRAFT", "draft202012"),
            control_plane_http_timeout_seconds=cls._env_float(
                "CONGINE_CONTROL_PLANE_HTTP_TIMEOUT", 10.0
            ),
            telemetry_enabled=cls._env_bool("CONGINE_TELEMETRY_ENABLED", True),
            telemetry_queue_size=cls._env_int("CONGINE_TELEMETRY_QUEUE_SIZE", 10_000),
            telemetry_batch_size=cls._env_int("CONGINE_TELEMETRY_BATCH_SIZE", 100),
            telemetry_max_retries=cls._env_int("CONGINE_TELEMETRY_MAX_RETRIES", 4),
            telemetry_backoff_base=cls._env_float(
                "CONGINE_TELEMETRY_BACKOFF_BASE", 0.5
            ),
            telemetry_backoff_max=cls._env_float("CONGINE_TELEMETRY_BACKOFF_MAX", 8.0),
            snapshot_dir=os.getenv("CONGINE_SNAPSHOT_DIR"),
            snapshot_lock_timeout_seconds=cls._env_float(
                "CONGINE_SNAPSHOT_LOCK_TIMEOUT", 10.0
            ),
            require_https=cls._env_bool("CONGINE_REQUIRE_HTTPS", True),
            allow_cleartext=cls._env_bool("CONGINE_ALLOW_CLEARTEXT", False),
            log_level=os.getenv("CONGINE_LOG_LEVEL", "INFO").upper(),
            log_safe_fields=cls._env_frozenset("CONGINE_LOG_SAFE_FIELDS"),
            log_redaction_enabled=cls._env_bool("CONGINE_LOG_REDACTION", True),
            breaker_failure_threshold=cls._env_int(
                "CONGINE_BREAKER_FAILURE_THRESHOLD", 5
            ),
            breaker_cooldown_seconds=cls._env_float(
                "CONGINE_BREAKER_COOLDOWN_SECONDS", 30.0
            ),
            deployment_mode=deployment_mode,
            max_payload_bytes=cls._env_int(
                "CONGINE_MAX_PAYLOAD_BYTES", DEFAULT_MAX_PAYLOAD_BYTES
            ),
            max_schema_bytes=cls._env_int(
                "CONGINE_MAX_SCHEMA_BYTES", DEFAULT_MAX_SCHEMA_BYTES
            ),
            max_contract_files=cls._env_int(
                "CONGINE_MAX_CONTRACT_FILES", DEFAULT_MAX_CONTRACT_FILES
            ),
            max_contract_file_bytes=cls._env_int(
                "CONGINE_MAX_CONTRACT_FILE_BYTES", DEFAULT_MAX_CONTRACT_FILE_BYTES
            ),
            max_stream_buffer_chars=cls._env_int(
                "CONGINE_MAX_STREAM_BUFFER_CHARS", DEFAULT_MAX_STREAM_BUFFER_CHARS
            ),
            max_http_response_bytes=cls._env_int(
                "CONGINE_MAX_HTTP_RESPONSE_BYTES", DEFAULT_MAX_HTTP_RESPONSE_BYTES
            ),
            start_background_services=cls._env_bool(
                "CONGINE_START_BACKGROUND_SERVICES", True
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate completeness and security policy (audit H4)."""
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
        if (
            self.require_https
            and not self.allow_cleartext
            and not self.base_url.lower().startswith("https://")
        ):
            raise CongineConfigurationError(
                "base_url must use https for a non-local control plane "
                "(set CONGINE_ALLOW_CLEARTEXT=true for development / internal "
                "deployments, or CONGINE_REQUIRE_HTTPS=false to disable the policy)"
            )

    def is_local_base_url(self) -> bool:
        """Return ``True`` if the control plane host is an exact loopback match.

        Uses parsed hostname (FIX-01) — substring false positives such as
        ``notlocalhost`` or ``localhost.evil.com`` are rejected.
        """
        parsed = urlparse(self.base_url or "")
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        return hostname in _LOCAL_HOSTS

    def effective_log_safe_fields(self) -> Optional[FrozenSet[str]]:
        """Return the log allowlist after applying non-local auto-redaction (FIX-08)."""
        if self.log_safe_fields is not None:
            return self.log_safe_fields
        if not self.log_redaction_enabled or self.is_local_base_url():
            return None
        return frozenset(
            {
                "contract_id",
                "contract_version",
                "status",
                "duration_ms",
                "rule",
                "field",
                "error_type",
                "breaches",
                "count",
                "attempt",
                "timeout_ms",
                "degraded",
            }
        )

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        normalized = raw.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        return normalized in {"1", "true", "yes", "on"}

    @staticmethod
    def _env_int(name: str, default: int) -> int:
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
    def _env_frozenset(name: str) -> "Optional[FrozenSet[str]]":
        raw = os.getenv(name)
        if raw is None:
            return None
        items = frozenset(part.strip() for part in raw.split(",") if part.strip())
        return items

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid float for {name}: {raw!r}"
            ) from exc


__all__ = ["Region", "FailMode", "DeploymentMode", "CongineConfig"]
