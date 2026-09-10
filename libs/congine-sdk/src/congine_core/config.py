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
from enum import Enum, StrEnum
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

# The only accepted boolean spellings (audit P0-07). Deliberately literal: a
# governance SDK must not guess what "maybe" or "yes please" was meant to mean.
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

#: Default control plane when ``CONGINE_BASE_URL`` is not set — i.e. local
#: development.
_DEFAULT_LOCAL_BASE_URL = "http://localhost:8080"

#: Shared default validation deadline, in milliseconds.
#:
#: Single source of truth (audit P0-07 / Q17). Both :class:`CongineConfig` and
#: :class:`ValidateContractUseCase` derive their default from this constant.
#: They previously disagreed — 100 via configuration, 15 in the use case's own
#: constructor — so a host that built the use case directly silently ran a
#: budget almost seven times tighter than the documented one.
#:
#: It lives in Layer 0 alongside the configuration it parameterises, which the
#: use-case layer already imports (:class:`FailMode`); no new dependency edge is
#: introduced and the reference still points inward.
DEFAULT_VALIDATION_TIMEOUT_MS = 100


class Region(str, Enum):
    """Deployment region label for the Congine control plane.

    .. important:: **Region is metadata. It does not select an endpoint.**

       An earlier change (audit Q1) mapped each region to a default
       ``base_url`` — ``https://api.{us,eu,apac}.congine.dev``. Those hostnames
       were never confirmed against a deployed control plane, so the mapping
       could send an API key to an endpoint nobody had verified. It has been
       **reverted** (audit P0-08): a governance SDK must never infer a
       credential destination.

       ``CONGINE_BASE_URL`` is now the only thing that selects a control plane.
       Setting ``CONGINE_REGION`` *without* it is a configuration error rather
       than a silent fall back to loopback — see
       :meth:`CongineConfig.base_url_from_env`.

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


class DeploymentMode(str, Enum):
    """Process deployment topology for container lifecycle policy."""

    SINGLE_TENANT = "single_tenant"
    MULTI_TENANT = "multi_tenant"


class ContractAdmissionMode(StrEnum):
    """How strictly contracts are admitted as active policy (audit P0-03/P0-04).

    :class:`enum.StrEnum`, not ``(str, Enum)`` like the older policy enums beside
    it. This value is machine-facing — it is reported by
    ``ServiceContainer.health()`` — and a plain ``(str, Enum)`` renders as
    ``"ContractAdmissionMode.STRICT"`` under ``str()`` and f-strings while
    serialising correctly through ``json.dumps``, so a single interpolation on
    the way to an operator leaks an implementation name. ``StrEnum`` renders as
    the value on every path. The pre-existing enums are deliberately left alone:
    changing them would alter output elsewhere and is out of this pass's scope.

    Defined here in Layer 0 beside :class:`FailMode` and :class:`DeploymentMode`
    because it is an organizational *policy* knob, and because Layer 0 may not
    import the domain. The admission logic that consumes it lives in
    :mod:`congine_core.domain.contract_admission`, which imports inward to here.

    .. important:: **``WARN`` relaxes compatibility, never correctness.** It can
       never admit a contract whose meaning CONGINE cannot determine — unknown
       types, empty unions, invalid regexes, ambiguous dotted keys, malformed
       grammar and clauses no active evaluator executes are refused in both
       modes. See :class:`~congine_core.domain.contract_admission.ContractAdmissionMode`
       usage notes for why a permissive migration mode would rebuild the exact
       false-safety failure this boundary removes.
    """

    STRICT = "strict"
    WARN = "warn"


class ContractSource(StrEnum):
    """Where contracts are loaded from (audit P0-07).

    Previously an unrestricted string compared against the literal ``"file"``,
    so ``CONGINE_CONTRACT_SOURCE=files`` — a plausible typo — silently selected
    the HTTP control plane instead. A typo must never change network topology,
    so the value is now validated and an unknown one is a configuration error.
    """

    HTTP = "http"
    FILE = "file"


#: Every enum-backed :class:`CongineConfig` field, normalized centrally by
#: ``__post_init__`` so a raw wire string can never survive into a runtime
#: identity check (audit P0-07 closeout).
#:
#: Four of these feed ``is`` comparisons in production code — ``fail_mode``
#: (``validate_contract_usecase``), ``deployment_mode`` (``langchain_handler``),
#: ``contract_source`` and ``contract_admission`` — where an un-normalized string
#: silently took the wrong branch. ``region`` carries no branch but is normalized
#: for consistency, so the rule has no exceptions to remember.
_ENUM_FIELDS: "dict[str, type[Enum]]" = {
    "region": Region,
    "fail_mode": FailMode,
    "contract_source": ContractSource,
    "deployment_mode": DeploymentMode,
    "contract_admission": ContractAdmissionMode,
}


def _accepted(enum_cls: "type[Enum]") -> str:
    """Render an enum's accepted wire values for an error message."""
    return ", ".join(sorted(str(m.value) for m in enum_cls))


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
    validation_timeout_ms: int = DEFAULT_VALIDATION_TIMEOUT_MS
    #: Optional per-stage caps inside the aggregate validation budget (P1.5).
    #: ``None`` means "inherit whatever aggregate budget remains when this stage
    #: starts", which is why the effective value varies with stage start time and
    #: cannot be reported as a fixed number.
    native_validation_timeout_ms: Optional[int] = None
    semantic_validation_timeout_ms: Optional[int] = None
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
    contract_source: ContractSource = ContractSource.HTTP
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

    # --- Contract admission (audit P0-03 / P0-04) ------------------------ #
    # STRICT refuses any contract whose meaning CONGINE cannot determine. WARN
    # adds migration advisories for enforceable legacy constructs; it cannot
    # admit an invalid or unenforceable contract.
    contract_admission: ContractAdmissionMode = ContractAdmissionMode.STRICT

    def __post_init__(self) -> None:
        """Normalize, then validate — the single instance-level boundary.

        Configuration must mean the same thing regardless of where it came from:
        :meth:`from_env`, direct Python construction, a test, or a future CLI or
        API adapter. Two defects made that untrue.

        **Enum fields accepted raw strings.** Every enum-backed field is
        ``str``-backed, so ``CongineConfig(fail_mode="strict")`` stored a plain
        ``str`` that compared equal to the member but failed the ``is`` identity
        checks the code actually branches on. The result was silent: a directly
        constructed ``fail_mode="strict"`` **degraded instead of raising**, and a
        ``deployment_mode="multi_tenant"`` bypassed the multi-tenant guard in the
        LangChain handler. Same class of failure for the P0-introduced
        ``contract_source`` and ``contract_admission``.

        **Validation ran on only one path.** :meth:`validate` was invoked solely
        by :meth:`from_env`, so a directly constructed config skipped the
        credential and HTTPS policy entirely.

        Both are fixed here, in this order — normalization first, so
        :meth:`validate` always sees canonical members rather than a mixed
        enum/string state. :meth:`validate` is *called*, never reimplemented:
        there is exactly one definition of the configuration invariants.

        ``object.__setattr__`` is required because the dataclass is frozen; this
        mirrors ``TelemetryEvent.__post_init__``.
        """
        for name, enum_cls in _ENUM_FIELDS.items():
            value = getattr(self, name)
            # Members are str subclasses, so this must precede the str branch.
            if isinstance(value, enum_cls):
                continue
            if not isinstance(value, str):
                raise CongineConfigurationError(
                    f"Invalid {name}: expected {enum_cls.__name__} or one of "
                    f"{_accepted(enum_cls)}, got {type(value).__name__}"
                )
            try:
                coerced = enum_cls(value.strip().lower())
            except ValueError as exc:
                raise CongineConfigurationError(
                    f"Invalid {name}: {value!r}. Accepted: {_accepted(enum_cls)}."
                ) from exc
            object.__setattr__(self, name, coerced)

        self._validate_stage_budgets()
        self.validate()

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
            # Same strip+lower rule __post_init__ applies, so env and direct
            # construction accept exactly the same inputs.
            return DeploymentMode(raw.strip().lower())
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid CONGINE_DEPLOYMENT_MODE: {raw!r}"
            ) from exc

    @staticmethod
    def base_url_from_env(region: Region) -> str:
        """Resolve the control-plane URL (audit P0-08).

        Only ``CONGINE_BASE_URL`` selects a control plane. Region is metadata and
        never infers a destination — the previous region→hostname mapping pointed
        at unconfirmed placeholder domains, so setting a region could ship an API
        key to an endpoint nobody had verified.

        Precedence:

        - ``CONGINE_BASE_URL`` set  → use it, whatever the region says.
        - Neither set               → loopback default (local development).
        - ``CONGINE_REGION`` set but no base URL → **configuration error.**

        The last case is deliberate. Setting a region declares a remote
        deployment; silently falling back to ``localhost`` for such a deployment
        would be precisely the quiet misconfiguration this pass removes. There is
        no separate "remote" deployment mode to key off — ``DeploymentMode``
        describes tenancy, and remoteness is derived from the URL itself — so the
        region flag is the honest signal of that intent.
        """
        explicit = os.getenv("CONGINE_BASE_URL")
        if explicit:
            return explicit
        if os.getenv("CONGINE_REGION"):
            raise CongineConfigurationError(
                f"CONGINE_REGION={region.value!r} declares a remote deployment, but "
                "CONGINE_BASE_URL is not set. Region is metadata and no longer "
                "selects an endpoint (the previous regional hostnames were "
                "unverified placeholders). Set CONGINE_BASE_URL explicitly."
            )
        return _DEFAULT_LOCAL_BASE_URL

    @classmethod
    def from_env(cls) -> "CongineConfig":
        """Load configuration from ``CONGINE_*`` environment variables."""
        try:
            region = Region(os.getenv("CONGINE_REGION", "us").strip().lower())
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid CONGINE_REGION: {os.getenv('CONGINE_REGION')!r}"
            ) from exc
        try:
            fail_mode = FailMode(
                os.getenv("CONGINE_FAIL_MODE", "degrade").strip().lower()
            )
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid CONGINE_FAIL_MODE: {os.getenv('CONGINE_FAIL_MODE')!r}"
            ) from exc
        try:
            contract_source = ContractSource(
                os.getenv("CONGINE_CONTRACT_SOURCE", "http").strip().lower()
            )
        except ValueError as exc:
            accepted = ", ".join(sorted(m.value for m in ContractSource))
            raise CongineConfigurationError(
                f"Invalid CONGINE_CONTRACT_SOURCE: "
                f"{os.getenv('CONGINE_CONTRACT_SOURCE')!r}. Accepted: {accepted}."
            ) from exc
        try:
            contract_admission = ContractAdmissionMode(
                os.getenv("CONGINE_CONTRACT_ADMISSION", "strict").strip().lower()
            )
        except ValueError as exc:
            accepted = ", ".join(sorted(m.value for m in ContractAdmissionMode))
            raise CongineConfigurationError(
                f"Invalid CONGINE_CONTRACT_ADMISSION: "
                f"{os.getenv('CONGINE_CONTRACT_ADMISSION')!r}. Accepted: {accepted}."
            ) from exc
        deployment_mode = cls.deployment_mode_from_env()

        config = cls(
            base_url=cls.base_url_from_env(region),
            api_key=os.getenv("CONGINE_API_KEY"),
            project_id=os.getenv("CONGINE_PROJECT_ID"),
            tenant_id=os.getenv("CONGINE_TENANT_ID"),
            region=region,
            validation_timeout_ms=cls._env_int(
                "CONGINE_TIMEOUT_MS", DEFAULT_VALIDATION_TIMEOUT_MS
            ),
            native_validation_timeout_ms=cls._env_optional_int(
                "CONGINE_NATIVE_TIMEOUT_MS"
            ),
            semantic_validation_timeout_ms=cls._env_optional_int(
                "CONGINE_SEMANTIC_TIMEOUT_MS"
            ),
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
            contract_source=contract_source,
            contracts_dir=cls._env_optional_path("CONGINE_CONTRACTS_DIR"),
            local_contracts_dir=cls._env_optional_path("CONGINE_LOCAL_CONTRACTS_DIR"),
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
            contract_admission=contract_admission,
        )
        # No validate() call here: construction validates (see __post_init__), so
        # validation has exactly one owner and no caller has to remember it.
        return config

    def _validate_stage_budgets(self) -> None:
        """Reject stage caps that could not mean what they appear to mean.

        Checked here rather than in :meth:`validate`, which returns early for a
        local ``base_url`` — a stage cap must be validated on every construction
        path, not only for remote deployments (G13).

        A cap larger than the aggregate budget is refused rather than silently
        clamped: it reads as "semantic may take 500 ms" while the aggregate would
        cut it off at 100 ms, and quietly honouring the smaller number is exactly
        the kind of gap between stated and actual policy this phase exists to
        close.
        """
        for name in ("native_validation_timeout_ms", "semantic_validation_timeout_ms"):
            value = getattr(self, name)
            if value is None:
                continue
            # bool is an int subclass; `True` must not read as a 1 ms budget.
            if isinstance(value, bool) or not isinstance(value, int):
                raise CongineConfigurationError(
                    f"Invalid {name}: expected a positive integer of milliseconds "
                    f"or None, got {type(value).__name__}"
                )
            if value <= 0:
                raise CongineConfigurationError(
                    f"Invalid {name}: must be greater than 0, got {value}"
                )
            if value > self.validation_timeout_ms:
                raise CongineConfigurationError(
                    f"Invalid {name}: {value}ms exceeds the aggregate "
                    f"validation_timeout_ms of {self.validation_timeout_ms}ms. A "
                    "stage cannot be given more time than the whole validation."
                )

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
        """Parse a boolean environment variable, **failing loudly** (audit P0-07).

        Previously any unrecognised text evaluated to ``False``, so
        ``CONGINE_TELEMETRY_ENABLED=TRUE!`` silently disabled telemetry and
        ``CONGINE_START_BACKGROUND_SERVICES=enabled`` silently disabled three
        subsystems. Numeric fields already failed loudly; booleans failed
        silently, and in one direction only. A typo must never quietly change
        deployment topology.

        The accepted set is deliberately small and literal — no natural-language
        truthiness such as ``"yes please"``.
        """
        raw = os.getenv(name)
        if raw is None:
            return default
        normalized = raw.strip().lower()
        if normalized in _FALSE_VALUES:
            return False
        if normalized in _TRUE_VALUES:
            return True
        accepted = ", ".join(sorted(_TRUE_VALUES | _FALSE_VALUES))
        raise CongineConfigurationError(
            f"Invalid boolean for {name}: {raw!r}. Accepted values: {accepted}."
        )

    @staticmethod
    def _env_optional_path(name: str) -> Optional[str]:
        """Read a path variable where empty and unset mean different things (P0-07).

        ``CONGINE_LOCAL_CONTRACTS_DIR=""`` — the ordinary shell and orchestrator
        idiom for "unset this" — used to select standalone mode pointed at an
        empty directory: no contracts loaded, no sync worker allocated to
        recover, and every guarded call raising. Empty is now an error, so the
        misconfiguration is visible at startup instead of at first request.

        unset → not selected · empty/whitespace → error · non-empty → use it.
        """
        raw = os.getenv(name)
        if raw is None:
            return None
        if not raw.strip():
            raise CongineConfigurationError(
                f"{name} is set but empty. Leave it unset to disable the feature, "
                "or provide a directory path."
            )
        return raw

    @staticmethod
    def _env_optional_int(name: str) -> "Optional[int]":
        """Read an optional integer env var.

        Unset means "inherit the remaining aggregate budget". An **empty** value
        is an error rather than a silent ``None``: ``CONGINE_NATIVE_TIMEOUT_MS=``
        almost always means a misconfigured deployment, and treating it as
        "unset" would hide that.
        """
        raw = os.getenv(name)
        if raw is None:
            return None
        if not raw.strip():
            raise CongineConfigurationError(
                f"Invalid integer for {name}: empty value. Unset the variable to "
                "inherit the aggregate budget."
            )
        try:
            return int(raw)
        except ValueError as exc:
            raise CongineConfigurationError(
                f"Invalid integer for {name}: {raw!r}"
            ) from exc

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


__all__ = [
    "Region",
    "FailMode",
    "DeploymentMode",
    "ContractSource",
    "ContractAdmissionMode",
    "CongineConfig",
    "DEFAULT_VALIDATION_TIMEOUT_MS",
]
