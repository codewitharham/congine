"""HTTP contract repository (Layer 4).

:class:`HttpContractRepository` implements
:class:`congine_core.ports.contract_repository.IContractRepository`,
fetching active contracts from the control plane over HTTP and persisting an
atomic on-disk snapshot for stale-ok degraded operation.

Snapshot security & isolation (audit C2): the snapshot path is **scoped per
tenant/project** (a hash of ``base_url|project_id|tenant_id``) and lives under a
**per-user, app-owned** directory — NOT the world-shared OS temp root — so two
tenants on one host cannot contaminate each other's cache and a local attacker
cannot pre-plant a predictable ``/tmp/congine_snapshot.json``. On load the file
is refused if it is a symlink or not owned by the current user, and the JSON
envelope shape is validated. Writes remain crash-atomic (temp file in the same
directory + :func:`os.replace`).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

import httpx

try:  # Advisory inter-process locking; degrades to atomic-replace-only if absent.
    import portalocker

    _PORTALOCKER_AVAILABLE = True
except ImportError:  # pragma: no cover - portalocker is a declared core dependency
    portalocker = None  # type: ignore[assignment]
    _PORTALOCKER_AVAILABLE = False

from congine_core.config import CongineConfig
from congine_core.exceptions import CongineSyncError
from congine_core.ports.logger import ILogger

#: Seconds to wait for the cross-process snapshot lock before giving up the write.
_SNAPSHOT_LOCK_TIMEOUT = 10.0


def _default_snapshot_dir() -> str:
    """Return a per-user, app-owned snapshot directory (not world-shared)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "congine", "snapshots")
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = xdg or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "congine", "snapshots")


def _scope_key(config: CongineConfig) -> str:
    """Stable per-tenant/project filename component (no secrets in the name)."""
    raw = "|".join(
        [config.base_url or "", config.project_id or "", config.tenant_id or ""]
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


class HttpContractRepository:
    """Fetch contracts from the control plane API with secure disk fallback."""

    def __init__(self, config: CongineConfig, logger: Optional[ILogger] = None) -> None:
        """Args:
        config: Runtime configuration (base URL, credentials, identifiers).
        logger: Optional structured logger for observability.
        """
        self.config = config
        self.logger = logger
        self._snapshot_dir = config.snapshot_dir or _default_snapshot_dir()
        self._snapshot_path = os.path.join(
            self._snapshot_dir, f"snapshot_{_scope_key(config)}.json"
        )
        # Separate lock file for boot single-flight (audit D-7). Distinct from
        # `<snapshot>.lock` (used by save_snapshot) so boot coordination and
        # write serialization do not contend with each other.
        self._boot_lock_path = os.path.join(
            self._snapshot_dir, f"boot_{_scope_key(config)}.lock"
        )

    @property
    def snapshot_lock_path(self) -> str:
        """Path of the per-scope file used for boot single-flight coordination.

        :class:`SyncContractsUseCase.sync_once_single_flight` locks this file
        with ``portalocker LOCK_EX | LOCK_NB`` so that under N-worker boot only
        the first worker fetches from the control plane; the rest fall through
        to the on-disk snapshot the first worker just wrote.
        """
        return self._boot_lock_path

    async def fetch_active_contracts(self) -> List[Dict]:
        """Fetch active contracts from the control plane.

        Tenant/project/api-key headers are attached to every request so the
        control plane can enforce isolation at the wire.

        Returns:
            The ``contracts`` list from the control-plane response.

        Raises:
            CongineSyncError: On any transport failure, non-2xx response, or a
                malformed body lacking the ``contracts`` key. Callers degrade to
                :meth:`load_snapshot` so a cold network never hard-fails boot.
        """
        headers = {
            "X-API-Key": self.config.api_key or "",
            "X-Project-ID": self.config.project_id or "",
            "X-Tenant-ID": self.config.tenant_id or "",
        }
        url = f"{self.config.base_url}/api/v1/contracts/active"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
            return data["contracts"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            if self.logger is not None:
                self.logger.error("Contract fetch failed", url=url, error=str(exc))
            raise CongineSyncError(
                f"Failed to fetch active contracts from {url}"
            ) from exc

    def load_snapshot(self) -> Optional[List[Dict]]:
        """Load contracts from the per-tenant disk snapshot (stale-ok fallback).

        Returns ``None`` when no usable snapshot exists. The file is refused if
        it is a symlink or not owned by the current user (snapshot-poisoning
        defence), and its envelope shape is validated.
        """
        path = self._snapshot_path
        try:
            if os.path.islink(path):
                self._warn("Refusing symlinked snapshot", path=path)
                return None
            if not self._owned_by_current_user(path):
                self._warn("Refusing snapshot not owned by current user", path=path)
                return None
            with open(path, "r", encoding="utf-8") as fh:
                snapshot = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return self._validate_envelope(snapshot)

    def save_snapshot(self, contracts: List[Dict]) -> None:
        """Persist *contracts* to the scoped snapshot path atomically.

        Multi-worker safety (audit C2): under Gunicorn/Uvicorn many worker
        processes write the *same* scoped snapshot concurrently. The write is
        wrapped in a :class:`portalocker` **advisory exclusive lock** on a
        sibling ``.lock`` file so the temp-write + ``os.replace`` sequence is
        serialized across processes — closing the Windows ``os.replace`` failure
        window and preventing interleaved writers. A worker that cannot acquire
        the lock within the timeout skips its write (snapshot persist is
        best-effort and must never break boot) rather than blocking or raising.

        Args:
            contracts: The contracts list to persist.
        """
        snapshot = {
            "version": "1.0",
            "contracts": contracts,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        os.makedirs(self._snapshot_dir, exist_ok=True)
        if os.name == "posix":
            try:  # tighten to owner-only; best-effort
                os.chmod(self._snapshot_dir, 0o700)
            except OSError:  # pragma: no cover - platform/permission dependent
                pass

        with self._snapshot_lock() as acquired:
            if not acquired:
                # Another process holds the lock and we timed out: it is writing
                # the very same fetched contracts, so dropping our write is safe.
                self._warn(
                    "Snapshot lock busy; skipping write", path=self._snapshot_path
                )
                return
            fd, temp_path = tempfile.mkstemp(dir=self._snapshot_dir, suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(snapshot, fh)
                os.replace(temp_path, self._snapshot_path)
            except Exception:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @contextlib.contextmanager
    def _snapshot_lock(self) -> "Iterator[bool]":
        """Hold an advisory cross-process lock for the snapshot write.

        Yields ``True`` while the exclusive lock is held, ``False`` if it could
        not be acquired within :data:`_SNAPSHOT_LOCK_TIMEOUT` (or if
        ``portalocker`` is unavailable, in which case the caller falls back to
        the still-atomic ``os.replace`` with no cross-process serialization).
        """
        if not _PORTALOCKER_AVAILABLE:
            yield True  # No advisory lock available; atomic replace still applies.
            return
        lock_path = f"{self._snapshot_path}.lock"
        # Non-blocking flag so the timeout is honoured: portalocker retries the
        # acquire until _SNAPSHOT_LOCK_TIMEOUT, then raises (blocking mode would
        # ignore the timeout and wait forever).
        lock = portalocker.Lock(
            lock_path,
            mode="a",
            timeout=_SNAPSHOT_LOCK_TIMEOUT,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        )
        try:
            lock.acquire()
        except portalocker.exceptions.LockException:
            yield False
            return
        try:
            yield True
        finally:
            with contextlib.suppress(Exception):
                lock.release()

    @staticmethod
    def _owned_by_current_user(path: str) -> bool:
        """Return ``True`` unless (on POSIX) the file is owned by another user."""
        if os.name != "posix":
            return True
        try:
            return os.stat(path).st_uid == os.getuid()
        except OSError:
            return True

    @staticmethod
    def _validate_envelope(snapshot: Any) -> Optional[List[Dict]]:
        """Validate the snapshot envelope; return its well-formed contracts."""
        if not isinstance(snapshot, dict):
            return None
        contracts = snapshot.get("contracts")
        if not isinstance(contracts, list):
            return None
        valid = [c for c in contracts if isinstance(c, dict)]
        return valid or None

    def _warn(self, message: str, **kwargs: Any) -> None:
        if self.logger is not None:
            self.logger.warning(message, **kwargs)
