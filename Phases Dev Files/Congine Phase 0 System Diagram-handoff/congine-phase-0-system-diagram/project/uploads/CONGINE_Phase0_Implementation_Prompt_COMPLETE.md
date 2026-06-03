# CONGINE SDK Phase 0: Complete Implementation Prompt
## Clean Build from Skeleton Code

---

## Executive Summary

The monorepo `libs/congine-sdk/src/congine_core/` currently contains **skeleton files with empty implementations**. This prompt defines the **complete, production-ready Phase 0 implementation** following strict SOLID principles, Layered Architecture, Dependency Injection, and Repository Pattern.

**Current State:** Skeleton structure exists (files present, imports stubbed, some docstrings)  
**Target State:** Full working implementation across 5 layers  
**Naming Convention:** All code uses `congine` (not `amce`)  
**Architecture:** Layered, decoupled, protocol-driven, zero circular dependencies

---

## Directory Structure (Target)

```
libs/congine-sdk/src/congine_core/
├── __init__.py                              # Public exports (Layer 5)
├── config.py                                # Configuration (shared)
├── exceptions.py                            # Canonical exceptions (Layer 1)
│
├── repositories/                            # LAYER 1: Abstractions (Protocols)
│   ├── __init__.py
│   ├── schema_storage.py                   # ISchemaStorage protocol
│   ├── contract_repository.py               # IContractRepository protocol
│   ├── event_bus.py                        # IEventBus protocol
│   └── logger.py                           # ILogger protocol
│
├── domain/                                  # LAYER 2: Pure Business Logic
│   ├── __init__.py
│   ├── models.py                           # Domain models (frozen dataclasses)
│   └── validator.py                        # RuleEngine + LocalValidator
│
├── usecases/                                # LAYER 3: Workflows
│   ├── __init__.py
│   └── validate_contract_usecase.py        # Orchestration logic
│
├── infrastructure/                          # LAYER 4: Concrete Implementations
│   ├── __init__.py
│   ├── lfu_cache.py                        # LFUCache (implements ISchemaStorage)
│   ├── http_contract_repository.py         # HTTP repo (implements IContractRepository)
│   ├── queue_event_bus.py                  # Queue bus (implements IEventBus)
│   ├── logger.py                           # Structured logger (implements ILogger)
│   └── timer.py                            # ValidationTimer (cross-platform timeout)
│
└── adapters/                                # LAYER 5: Framework Entry Points
    ├── __init__.py
    ├── dependency_injection.py              # ServiceContainer (DI wiring)
    └── guard.py                            # @congine_guard decorator
```

---

## Implementation Details by Layer

### LAYER 1: REPOSITORIES (Abstractions/Protocols)

#### `repositories/__init__.py`
**Exports:** `ISchemaStorage, IContractRepository, IEventBus, ILogger`

```python
from .schema_storage import ISchemaStorage
from .contract_repository import IContractRepository
from .event_bus import IEventBus
from .logger import ILogger

__all__ = [
    "ISchemaStorage",
    "IContractRepository",
    "IEventBus",
    "ILogger",
]
```

#### `repositories/schema_storage.py`
**Purpose:** Abstract interface for schema caching/retrieval  
**Key Methods:**
- `get(contract_id: str) -> Optional[Dict[str, Any]]`
- `put(contract_id: str, schema: Dict[str, Any], ttl_seconds: int) -> None`
- `clear() -> None`
- `exists(contract_id: str) -> bool`

**Notes:**
- Use `typing.Protocol` (structural typing, not inheritance)
- No implementation logic — pure interface
- Return `None` if cache miss or TTL expired

#### `repositories/contract_repository.py`
**Purpose:** Abstract interface for fetching contracts  
**Key Methods:**
- `async fetch_active_contracts() -> List[Dict]` (HTTP to control plane)
- `load_snapshot() -> Optional[List[Dict]]` (disk fallback)
- `save_snapshot(contracts: List[Dict]) -> None` (atomic write)

**Notes:**
- Async method for I/O operations
- Snapshot location: `/tmp/congine_snapshot.json`
- Atomic writes using `tempfile + os.replace()`

#### `repositories/event_bus.py`
**Purpose:** Abstract interface for event publishing  
**Key Methods:**
- `publish(event: TelemetryEvent) -> None` (fire-and-forget)

**Notes:**
- Non-blocking, background processing
- Events may be dropped if queue full (graceful degradation)

#### `repositories/logger.py`
**Purpose:** Abstract interface for structured logging  
**Key Methods:**
- `info(message: str, **kwargs) -> None`
- `error(message: str, **kwargs) -> None`
- `warning(message: str, **kwargs) -> None`
- `debug(message: str, **kwargs) -> None`

**Notes:**
- Structured (dict-like) logging
- Key-value extras passed via `**kwargs`

---

### LAYER 2: DOMAIN (Pure Business Logic)

#### `domain/__init__.py`
**Exports:** `BreachDetail, ValidationResult, TelemetryEvent, RuleEngine, LocalValidator, IValidator`

#### `domain/models.py`
**Purpose:** Domain model definitions (frozen dataclasses, zero framework dependencies)

**Models to implement:**

```python
@dataclass(frozen=True)
class BreachDetail:
    """Single validation breach."""
    rule: str                    # "TYPE_MATCH", "FIELD_PRESENCE", etc.
    field: str                   # Field name (or "<root>" for whole payload)
    message: Optional[str] = None
```

```python
@dataclass(frozen=True)
class ValidationResult:
    """Result of validation."""
    status: str                  # "pass" or "fail"
    breaches: tuple = ()         # Tuple[BreachDetail, ...]
    duration_ms: float = 0.0
    degraded: bool = False       # True if timeout or error fallback
    
    def is_pass(self) -> bool:
        return self.status == "pass"
```

```python
@dataclass
class TelemetryEvent:
    """Validation telemetry event."""
    contract_id: str
    contract_version: str
    status: str                  # "pass" or "fail"
    duration_ms: float
    breach_details: list = None  # List[Dict]
    created_at: datetime = None
    
    def __post_init__(self):
        if self.breach_details is None:
            self.breach_details = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
```

#### `domain/validator.py`
**Purpose:** Core validation logic (6 rules + orchestration)

**RuleEngine (static methods for 6 rules):**

```python
class RuleEngine:
    """Pure validation rules — no I/O, no state."""
    
    @staticmethod
    def FIELD_PRESENCE(payload: dict, required_fields: list) -> List[BreachDetail]:
        """Rule 1: Required fields must exist."""
        # For each field in required_fields:
        #   If field not in payload → add BreachDetail(rule="FIELD_PRESENCE", field=field)
    
    @staticmethod
    def TYPE_MATCH(payload: dict, schema_properties: dict) -> List[BreachDetail]:
        """Rule 2: Field types must match schema."""
        # For each field in schema_properties:
        #   If payload[field] type != schema type → add breach
        # Support types: "string", "number", "integer", "boolean", "object", "array"
    
    @staticmethod
    def ENUM_VALUES(payload: dict, enum_map: dict) -> List[BreachDetail]:
        """Rule 3: Enum fields must match allowed values."""
        # For each field in enum_map:
        #   If payload[field] not in enum_map[field]["enum"] → add breach
    
    @staticmethod
    def RANGE_CHECK(payload: dict, range_map: dict) -> List[BreachDetail]:
        """Rule 4: Numeric fields must be within range."""
        # For each field in range_map:
        #   If payload[field] < min OR > max → add breach
    
    @staticmethod
    def NULL_GUARD(payload: dict, null_forbidden: list) -> List[BreachDetail]:
        """Rule 5: Certain fields cannot be null/None."""
        # For each field in null_forbidden:
        #   If payload[field] is None → add breach
    
    @staticmethod
    def REGEX_PATTERN(payload: dict, pattern_map: dict) -> List[BreachDetail]:
        """Rule 6: String fields must match regex."""
        # For each field in pattern_map:
        #   If payload[field] not match pattern_map[field]["pattern"] → add breach
```

**IValidator Protocol:**
```python
class IValidator(Protocol):
    """Interface: Validation strategy."""
    
    def validate(self, payload: dict, schema: dict) -> ValidationResult:
        """Validate payload against schema."""
        ...
```

**LocalValidator (composition-based):**
```python
class LocalValidator:
    """Local validation — apply all 6 rules."""
    
    def __init__(self, rules: list = None):
        """
        Constructor injection of rules.
        
        Args:
            rules: List of (rule_name, rule_function) tuples.
                   If None, use all 6 rules by default.
        """
        if rules is None:
            self.rules = [
                ("FIELD_PRESENCE", RuleEngine.FIELD_PRESENCE),
                ("TYPE_MATCH", RuleEngine.TYPE_MATCH),
                ("ENUM_VALUES", RuleEngine.ENUM_VALUES),
                ("RANGE_CHECK", RuleEngine.RANGE_CHECK),
                ("NULL_GUARD", RuleEngine.NULL_GUARD),
                ("REGEX_PATTERN", RuleEngine.REGEX_PATTERN),
            ]
        else:
            self.rules = rules
    
    def validate(self, payload: dict, schema: dict) -> ValidationResult:
        """Compose all rules and return result."""
        if not isinstance(payload, dict):
            return ValidationResult(
                status="fail",
                breaches=(BreachDetail(rule="TYPE_MATCH", field="<root>"),)
            )
        
        all_breaches = []
        
        # Compose rules
        for rule_name, rule_fn in self.rules:
            if rule_name == "FIELD_PRESENCE":
                all_breaches.extend(rule_fn(payload, schema.get("required", [])))
            # ... etc for other rules, extracting params from schema
        
        status = "pass" if not all_breaches else "fail"
        return ValidationResult(status=status, breaches=tuple(all_breaches))
```

**Notes:**
- Zero external dependencies (no frameworks)
- Composition over inheritance (rules are passed in)
- All methods pure functions (no side effects)

---

### LAYER 3: USECASES (Workflows/Orchestration)

#### `usecases/__init__.py`
**Exports:** `ValidateContractUseCase`

#### `usecases/validate_contract_usecase.py`
**Purpose:** Orchestrate validation workflow (fetch schema → validate → publish event)

**Implementation:**

```python
class ValidateContractUseCase:
    """Validate output against contract (orchestration)."""
    
    def __init__(
        self,
        schema_storage: ISchemaStorage,       # ← Injected abstraction
        validator: IValidator,                # ← Injected abstraction
        event_bus: IEventBus,                 # ← Injected abstraction
        logger: ILogger,                      # ← Injected abstraction
        timer: ValidationTimer,               # ← Injected concrete utility
        timeout_ms: int = 15,
    ):
        """Constructor injection of all dependencies."""
        self.schema_storage = schema_storage
        self.validator = validator
        self.event_bus = event_bus
        self.logger = logger
        self.timer = timer
        self.timeout_ms = timeout_ms
    
    def execute(
        self,
        payload: dict,
        contract_id: str,
        contract_version: str,
    ) -> ValidationResult:
        """
        Execute validation workflow:
        1. Fetch schema from storage (abstraction)
        2. Validate with timeout (domain logic)
        3. Publish event (abstraction, fire-and-forget)
        """
        
        # Step 1: Fetch schema
        schema = self.schema_storage.get(contract_id)
        if schema is None:
            self.logger.error(
                "Schema not found",
                contract_id=contract_id,
            )
            raise ValueError(f"Schema {contract_id} not found")
        
        # Step 2: Validate with timeout
        def do_validate():
            return self.validator.validate(payload, schema)
        
        try:
            result = self.timer.run_with_timeout(do_validate, self.timeout_ms)
        except TimeoutError:
            self.logger.warning(
                "Validation timeout",
                contract_id=contract_id,
                timeout_ms=self.timeout_ms,
            )
            result = ValidationResult(status="fail", degraded=True)
        except Exception as e:
            self.logger.error(
                "Validation error",
                contract_id=contract_id,
                error=str(e),
            )
            result = ValidationResult(status="fail", degraded=True)
        
        # Step 3: Publish event (fire-and-forget)
        event = TelemetryEvent(
            contract_id=contract_id,
            contract_version=contract_version,
            status=result.status,
            duration_ms=result.duration_ms,
            breach_details=[
                {
                    "rule": b.rule,
                    "field": b.field,
                    "message": b.message,
                }
                for b in result.breaches
            ],
        )
        self.event_bus.publish(event)
        
        return result
```

**Notes:**
- All dependencies injected via `__init__`
- Pure orchestration (no business logic)
- Error handling and logging for observability

---

### LAYER 4: INFRASTRUCTURE (Concrete Implementations)

#### `infrastructure/__init__.py`
**Exports:** `LFUCache, HttpContractRepository, QueueEventBus, StructuredLogger, ValidationTimer`

#### `infrastructure/lfu_cache.py`
**Purpose:** O(1) LFU Cache with TTL (implements `ISchemaStorage`)

**Key Implementation Details:**

```python
class LFUCache(ISchemaStorage):
    """LFU cache with O(1) operations and TTL."""
    
    def __init__(self, capacity: int = 500, ttl_seconds: int = 300):
        """
        Args:
            capacity: Maximum schemas to cache (LRU eviction when full)
            ttl_seconds: Time-to-live for each cached schema
        """
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self._key_to_value = {}      # contract_id → (schema, expire_time)
        self._key_to_freq = {}       # contract_id → access_frequency
        self._freq_to_keys = {}      # frequency → OrderedDict of keys
        self._min_freq = 0
        self._lock = threading.RLock()
    
    def get(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve schema. Increment frequency. Return None if missing/expired."""
        # Thread-safe with RLock
        # Check expiration timestamp
        # Increment frequency counter
        # Return value or None
    
    def put(self, contract_id: str, schema: Dict[str, Any], ttl_seconds: int = None) -> None:
        """Store schema with TTL. Evict LFU if at capacity."""
        # Thread-safe with RLock
        # If capacity full → evict least-frequently-used
        # Use atomic timestamp (time.time() + ttl)
    
    def clear(self) -> None:
        """Clear all cached schemas."""
        # Thread-safe clear
    
    def exists(self, contract_id: str) -> bool:
        """Check if key exists and not expired."""
        # Return True/False
    
    # Private helpers
    def _increment_freq(self, key):
        """Increment frequency and reorganize internal structures."""
    
    def _evict_lfu(self):
        """Find and evict least-frequently-used key."""
    
    def _evict_key(self, key):
        """Remove key from all internal dicts."""
```

**Algorithm:**
- Use Ketan Shah's O(1) LFU algorithm
- `_key_to_value` maps key → value
- `_key_to_freq` maps key → access count
- `_freq_to_keys` maps frequency → OrderedDict (maintains insertion order)
- On `get()`: increment frequency, reorganize
- On `put()` at capacity: evict lowest frequency, FIFO within that frequency
- Thread-safe using `threading.RLock()`

#### `infrastructure/http_contract_repository.py`
**Purpose:** HTTP contract repository (implements `IContractRepository`)

**Implementation:**

```python
class HttpContractRepository(IContractRepository):
    """Fetch contracts from control plane API."""
    
    def __init__(self, config: CongineConfig, logger: ILogger = None):
        """
        Args:
            config: Configuration with base_url, api_key, project_id, tenant_id
            logger: Optional logger for observability
        """
        self.config = config
        self.logger = logger
    
    async def fetch_active_contracts(self) -> List[Dict]:
        """
        Fetch active contracts from control plane.
        
        HTTP Call:
            GET /api/v1/contracts/active
            Headers:
                X-API-Key: config.api_key
                X-Project-ID: config.project_id
                X-Tenant-ID: config.tenant_id
        
        Response (expected):
            {
                "contracts": [
                    {
                        "id": "sentiment-v1",
                        "version": "1.0.0",
                        "schema": {...},
                    },
                    ...
                ]
            }
        """
        headers = {
            "X-API-Key": self.config.api_key,
            "X-Project-ID": self.config.project_id,
            "X-Tenant-ID": self.config.tenant_id,
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.config.base_url}/api/v1/contracts/active",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data["contracts"]
    
    def load_snapshot(self) -> Optional[List[Dict]]:
        """Load contracts from disk snapshot (stale-ok fallback)."""
        try:
            with open("/tmp/congine_snapshot.json", 'r') as f:
                snapshot = json.load(f)
            return snapshot.get("contracts")
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    
    def save_snapshot(self, contracts: List[Dict]) -> None:
        """
        Save contracts to disk atomically.
        
        File format:
            {
                "version": "1.0",
                "contracts": [...],
                "fetched_at": "ISO-8601-timestamp"
            }
        
        Atomicity: Write to temp file, then os.replace()
        """
        snapshot = {
            "version": "1.0",
            "contracts": contracts,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        }
        
        fd, temp_path = tempfile.mkstemp(dir="/tmp", suffix=".json")
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(snapshot, f)
            os.replace(temp_path, "/tmp/congine_snapshot.json")
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
```

#### `infrastructure/queue_event_bus.py`
**Purpose:** Queue-based event bus (implements `IEventBus`)

**Implementation:**

```python
class QueueEventBus(IEventBus):
    """Fire-and-forget event publishing via background queue."""
    
    def __init__(self, logger: ILogger = None, max_queue_size: int = 10_000):
        """
        Args:
            logger: Optional logger
            max_queue_size: Max events in queue before dropping
        """
        self._queue = queue.Queue(maxsize=max_queue_size)
        self._logger = logger
        self._daemon = threading.Thread(target=self._drain_loop, daemon=True)
        self._daemon.start()
    
    def publish(self, event: TelemetryEvent) -> None:
        """Publish event (non-blocking). Drop silently if queue full."""
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            if self._logger:
                self._logger.warning(
                    "Event queue full, dropping event",
                    contract_id=event.contract_id,
                )
    
    def _drain_loop(self):
        """Background thread: drain events and ship to telemetry service."""
        while True:
            try:
                event = self._queue.get(timeout=1.0)
                # TODO: Ship to telemetry endpoint (POST to control plane)
                if self._logger:
                    self._logger.debug(
                        "Event published",
                        contract_id=event.contract_id,
                    )
            except queue.Empty:
                pass
            except Exception as e:
                if self._logger:
                    self._logger.error(
                        "Event drain error",
                        error=str(e),
                    )
```

#### `infrastructure/logger.py`
**Purpose:** Structured JSON logger (implements `ILogger`)

**Implementation:**

```python
class StructuredLogger(ILogger):
    """JSON-formatted structured logging to stdout."""
    
    def __init__(self, name: str = "congine"):
        """
        Args:
            name: Logger name (included in each log entry)
        """
        self.name = name
    
    def _log(self, level: str, message: str, **kwargs):
        """Internal log method."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "logger": self.name,
            "message": message,
            **kwargs,
        }
        print(json.dumps(entry))
    
    def info(self, message: str, **kwargs) -> None:
        self._log("INFO", message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        self._log("ERROR", message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        self._log("WARNING", message, **kwargs)
    
    def debug(self, message: str, **kwargs) -> None:
        self._log("DEBUG", message, **kwargs)
```

#### `infrastructure/timer.py`
**Purpose:** Cross-platform timeout wrapper (Windows-safe)

**Implementation:**

```python
class ValidationTimer:
    """Cross-platform timeout runner (Windows-safe)."""
    
    def __init__(self):
        """Initialize executor pool."""
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=10,
            thread_name_prefix="congine_timer",
        )
        atexit.register(self._cleanup)
    
    def run_with_timeout(
        self,
        func: Callable,
        timeout_ms: int,
    ) -> Any:
        """
        Run function with timeout.
        
        Args:
            func: Callable to run
            timeout_ms: Timeout in milliseconds
        
        Returns:
            Result of func()
        
        Raises:
            TimeoutError: If timeout exceeded
        
        Notes:
            Uses ThreadPoolExecutor (cross-platform, Windows-safe).
            Cannot kill thread mid-execution; will leak thread if timeout.
        """
        future = self._executor.submit(func)
        timeout_seconds = timeout_ms / 1000.0
        
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Timeout after {timeout_ms}ms")
    
    def _cleanup(self):
        """Cleanup executor on exit."""
        self._executor.shutdown(wait=False)
```

---

### LAYER 5: ADAPTERS (Framework Entry Points)

#### `adapters/__init__.py`
**Exports:** `ServiceContainer, congine_guard`

#### `adapters/dependency_injection.py`
**Purpose:** DI container that wires all dependencies

**Implementation:**

```python
class ServiceContainer:
    """Dependency Injection container."""
    
    def __init__(self, config: CongineConfig):
        """
        Assemble all layers top-to-bottom.
        
        Order matters: Lower layers instantiated first, then injected into upper layers.
        """
        self.config = config
        
        # LAYER 4: Infrastructure (concrete implementations)
        self.logger = StructuredLogger("congine")
        self.timer = ValidationTimer()
        self.schema_storage = LFUCache(
            capacity=config.cache_capacity,
            ttl_seconds=config.cache_ttl_seconds,
        )
        self.contract_repository = HttpContractRepository(config, self.logger)
        self.event_bus = QueueEventBus(self.logger)
        
        # LAYER 2: Domain (pure business logic)
        self.validator = LocalValidator()  # Uses default 6 rules
        
        # LAYER 3: Use Cases (orchestration)
        self.validate_contract_usecase = ValidateContractUseCase(
            schema_storage=self.schema_storage,
            validator=self.validator,
            event_bus=self.event_bus,
            logger=self.logger,
            timer=self.timer,
            timeout_ms=config.validation_timeout_ms,
        )
    
    @classmethod
    def from_env(cls) -> "ServiceContainer":
        """Load config from environment and create container."""
        config = CongineConfig.from_env()
        return cls(config)
```

**Notes:**
- Order: Infrastructure → Domain → Usecases
- All dependencies passed via constructor (no globals)
- Can be instantiated multiple times or as singleton

#### `adapters/guard.py`
**Purpose:** `@congine_guard` decorator

**Implementation:**

```python
def congine_guard(
    contract_id: str,
    version: str = "latest",
    container: ServiceContainer = None,
) -> Callable:
    """
    Decorator for validating function output against Congine contracts.
    
    Args:
        contract_id: Contract ID (e.g., "sentiment-v1")
        version: Contract version (default: "latest")
        container: ServiceContainer (if None, load from env)
    
    Usage:
        # Option 1: Inject container
        container = ServiceContainer.from_env()
        
        @congine_guard(contract_id="sentiment-v1", container=container)
        def analyze(text: str) -> dict:
            return {"score": 0.8}
        
        # Option 2: Load from env dynamically
        @congine_guard(contract_id="sentiment-v1")
        def analyze(text: str) -> dict:
            return {"score": 0.8}
    
    Returns:
        Wrapper that validates output and includes validation_result
    """
    
    def decorator(fn: Callable) -> Callable:
        # Resolve container
        ctx = container or ServiceContainer.from_env()
        
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs) -> dict:
            # Execute original function
            output = fn(*args, **kwargs)
            
            # Validate via use case
            validation_result = ctx.validate_contract_usecase.execute(
                payload=output,
                contract_id=contract_id,
                contract_version=version,
            )
            
            # Return both
            return {
                "output": output,
                "validation_result": validation_result,
            }
        
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs) -> dict:
            # Execute original function
            output = await fn(*args, **kwargs)
            
            # Validate via use case (same, validation is sync)
            validation_result = ctx.validate_contract_usecase.execute(
                payload=output,
                contract_id=contract_id,
                contract_version=version,
            )
            
            # Return both
            return {
                "output": output,
                "validation_result": validation_result,
            }
        
        # Detect if async
        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
```

---

### ROOT FILES

#### `config.py`
**Purpose:** Configuration management

**Implementation:**

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class Region(str, Enum):
    """Deployment region."""
    US = "us"      # Virginia
    EU = "eu"      # Frankfurt (GDPR)
    APAC = "apac"  # Singapore

class FailMode(str, Enum):
    """Behavior on validation failure."""
    STRICT = "strict"    # Fail immediately
    DEGRADE = "degrade"  # Log and continue
    SILENT = "silent"    # Ignore failures

@dataclass
class CongineConfig:
    """Congine SDK configuration."""
    
    # Control plane
    base_url: str
    api_key: str
    project_id: str
    tenant_id: str
    region: Region
    
    # Validation
    validation_timeout_ms: int = 15
    fail_mode: FailMode = FailMode.DEGRADE
    
    # Cache
    cache_capacity: int = 500
    cache_ttl_seconds: int = 300
    
    @classmethod
    def from_env(cls) -> "CongineConfig":
        """Load configuration from environment variables."""
        import os
        
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
```

#### `exceptions.py`
**Purpose:** Canonical Congine exceptions (Tier 1)

**Implementation:**

```python
class CongineValidationError(Exception):
    """Validation logic breach (includes contract violations)."""
    pass

class CongineContractNotFoundError(Exception):
    """Schema/contract not found."""
    pass

class CongineConfigurationError(Exception):
    """Configuration is invalid."""
    pass

class CongineSyncError(Exception):
    """Synchronization with control plane failed."""
    pass

class CongineCacheError(Exception):
    """Cache operation failed."""
    pass

class CongineTelemetryError(Exception):
    """Telemetry publishing failed."""
    pass

# Tier 2: Semantic aliases (for backwards compatibility)
ContractBreachException = CongineValidationError
SchemaCacheMissException = CongineContractNotFoundError
ValidationTimeoutException = CongineValidationError
TenantIsolationViolationException = CongineValidationError
```

#### `__init__.py` (Root)
**Purpose:** Public API exports

**Implementation:**

```python
# Layer 1: Abstractions
from .repositories import (
    ISchemaStorage,
    IContractRepository,
    IEventBus,
    ILogger,
)

# Layer 2: Domain
from .domain import (
    BreachDetail,
    ValidationResult,
    TelemetryEvent,
    RuleEngine,
    LocalValidator,
)

# Layer 3: Use Cases
from .usecases import ValidateContractUseCase

# Layer 4: Infrastructure
from .infrastructure import (
    LFUCache,
    HttpContractRepository,
    QueueEventBus,
    StructuredLogger,
    ValidationTimer,
)

# Layer 5: Adapters
from .adapters import (
    ServiceContainer,
    congine_guard,
)

# Config & Exceptions
from .config import CongineConfig, Region, FailMode
from .exceptions import (
    CongineValidationError,
    CongineContractNotFoundError,
    CongineConfigurationError,
    CongineSyncError,
    CongineCacheError,
    CongineTelemetryError,
    # Aliases
    ContractBreachException,
    SchemaCacheMissException,
    ValidationTimeoutException,
    TenantIsolationViolationException,
)

__version__ = "0.1.0"
__all__ = [
    # Abstractions
    "ISchemaStorage",
    "IContractRepository",
    "IEventBus",
    "ILogger",
    # Domain
    "BreachDetail",
    "ValidationResult",
    "TelemetryEvent",
    "RuleEngine",
    "LocalValidator",
    # Use Cases
    "ValidateContractUseCase",
    # Infrastructure
    "LFUCache",
    "HttpContractRepository",
    "QueueEventBus",
    "StructuredLogger",
    "ValidationTimer",
    # Adapters
    "ServiceContainer",
    "congine_guard",
    # Config
    "CongineConfig",
    "Region",
    "FailMode",
    # Exceptions
    "CongineValidationError",
    "CongineContractNotFoundError",
    "CongineConfigurationError",
    "CongineSyncError",
    "CongineCacheError",
    "CongineTelemetryError",
    "ContractBreachException",
    "SchemaCacheMissException",
    "ValidationTimeoutException",
    "TenantIsolationViolationException",
]
```

---

## Implementation Checklist

### Step 1: Verify Skeleton Structure
- [ ] Navigate to `libs/congine-sdk/src/congine_core/`
- [ ] Confirm all directories and empty files exist (as shown in target structure)
- [ ] No circular imports in existing code

### Step 2: Implement LAYER 1 (Abstractions)
- [ ] `repositories/schema_storage.py` — `ISchemaStorage` protocol
- [ ] `repositories/contract_repository.py` — `IContractRepository` protocol
- [ ] `repositories/event_bus.py` — `IEventBus` protocol
- [ ] `repositories/logger.py` — `ILogger` protocol
- [ ] `repositories/__init__.py` — Export all 4

### Step 3: Implement LAYER 2 (Domain)
- [ ] `domain/models.py` — `BreachDetail`, `ValidationResult`, `TelemetryEvent` (frozen dataclasses)
- [ ] `domain/validator.py` — `RuleEngine` (6 static methods), `LocalValidator` (composition)
- [ ] `domain/__init__.py` — Export models + validator classes

### Step 4: Implement LAYER 3 (Use Cases)
- [ ] `usecases/validate_contract_usecase.py` — `ValidateContractUseCase` (constructor DI, execute workflow)
- [ ] `usecases/__init__.py` — Export usecase

### Step 5: Implement LAYER 4 (Infrastructure)
- [ ] `infrastructure/lfu_cache.py` — `LFUCache` (O(1) LFU, TTL, thread-safe)
- [ ] `infrastructure/http_contract_repository.py` — `HttpContractRepository` (async fetch, snapshot fallback)
- [ ] `infrastructure/queue_event_bus.py` — `QueueEventBus` (background queue, fire-and-forget)
- [ ] `infrastructure/logger.py` — `StructuredLogger` (JSON to stdout)
- [ ] `infrastructure/timer.py` — `ValidationTimer` (ThreadPoolExecutor, cross-platform)
- [ ] `infrastructure/__init__.py` — Export all 5

### Step 6: Implement LAYER 5 (Adapters)
- [ ] `adapters/dependency_injection.py` — `ServiceContainer` (wire all layers)
- [ ] `adapters/guard.py` — `@congine_guard` decorator (sync + async support)
- [ ] `adapters/__init__.py` — Export container + decorator

### Step 7: Implement Root Files
- [ ] `config.py` — `CongineConfig`, `Region`, `FailMode` enums
- [ ] `exceptions.py` — 6 canonical exceptions + tier 2 aliases
- [ ] `__init__.py` — Public exports (all 25+ items)

### Step 8: Validation
- [ ] All files import cleanly (no circular dependencies)
- [ ] All abstractions used (no direct instantiation of concrete classes in domain/usecases)
- [ ] All exceptions importable from `congine_core`
- [ ] Example usage works:
  ```python
  from congine_core import ServiceContainer, congine_guard
  
  container = ServiceContainer.from_env()
  
  @congine_guard(contract_id="sentiment-v1", container=container)
  def analyze(text: str) -> dict:
      return {"score": 0.8}
  
  result = analyze("Great!")
  assert "output" in result
  assert "validation_result" in result
  ```

---

## Key Design Principles (Non-Negotiable)

1. **Layering:** No upward dependency. Domain knows nothing of Infrastructure.
2. **Protocols:** Use `typing.Protocol` for abstractions, not base classes.
3. **Constructor Injection:** All dependencies via `__init__`, not globals.
4. **Composition:** Rules composed, not inherited.
5. **Pure Domain:** `domain/` has zero external dependencies (no `httpx`, no `redis`, etc.).
6. **Thread Safety:** Shared state (cache, queue) protected with locks.
7. **Atomicity:** File writes via `tempfile + os.replace()`.
8. **Cross-Platform:** Timeout uses `ThreadPoolExecutor`, not `signal.alarm()`.
9. **Loose Coupling:** All dependencies are abstractions, enabling easy mocking.
10. **Fire-and-Forget:** Event bus drops events silently if queue full (graceful degradation).

---

## File Dependencies (Correct Order to Implement)

```
config.py                           (no internal deps)
exceptions.py                       (no internal deps)

repositories/                       (no internal deps)
  → schema_storage.py
  → contract_repository.py
  → event_bus.py
  → logger.py

domain/                             (depends on: nothing)
  → models.py
  → validator.py

infrastructure/                     (depends on: config, exceptions, domain)
  → timer.py
  → logger.py
  → lfu_cache.py
  → http_contract_repository.py
  → queue_event_bus.py

usecases/                           (depends on: repositories, domain, infrastructure)
  → validate_contract_usecase.py

adapters/                           (depends on: everything)
  → dependency_injection.py
  → guard.py

__init__.py (root)                  (depends on: all above)
```

---

## Testing Strategy (Skeleton Provided Separately)

Each layer gets unit tests:
- **Layer 1:** Mock tests (trivial, protocols not instantiable)
- **Layer 2:** Pure logic tests (no fixtures, deterministic)
- **Layer 3:** Integration tests (mock repositories)
- **Layer 4:** Integration tests (mock HTTP, real cache/queue)
- **Layer 5:** End-to-end tests (full container)

Target: **>80% coverage, >50 assertions per module**

---

## Success Criteria

✅ All files implemented with real code (not stubs)  
✅ No circular imports  
✅ All abstractions used consistently  
✅ Example usage code runs without error  
✅ All public APIs exported from `congine_core/__init__.py`  
✅ Configuration loads from environment  
✅ Cache operates in O(1)  
✅ Decorator works with sync and async functions  
✅ Thread-safe (cache, queue)  
✅ Tests pass with >80% coverage

---

## Notes for Implementation

- **Do not skip abstractions layer** — This is the most important part
- **Composition over inheritance** — Pass rules to LocalValidator, don't subclass
- **Error handling:** All external I/O wrapped in try-except with logging
- **Naming:** Stick to `congine_*` (not `amce_*`)
- **Import organization:** Use `from .module import Class` (relative imports within package)
- **Docstrings:** Every class and method must have docstring with Args, Returns, Raises
- **Type hints:** Full type hints throughout (no `Any` unless unavoidable)

---

**This is a complete, production-ready Phase 0 implementation specification. Proceed with Layer 1.**
