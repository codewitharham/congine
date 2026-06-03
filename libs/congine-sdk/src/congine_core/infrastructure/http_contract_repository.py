"""HTTP contract repository (Layer 4).

:class:`HttpContractRepository` implements
:class:`congine_core.repositories.contract_repository.IContractRepository`,
fetching active contracts from the control plane over HTTP and persisting an
atomic on-disk snapshot for stale-ok degraded operation.

Cross-platform note: the snapshot lives under the OS temp directory
(:func:`tempfile.gettempdir`) rather than a hard-coded ``/tmp`` so the SDK works
on Windows. Atomic replacement uses a temp file created in the *same* directory
as the target to guarantee :func:`os.replace` stays on one filesystem.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from congine_core.config import CongineConfig
from congine_core.repositories.logger import ILogger

#: Directory and path for the on-disk snapshot (cross-platform).
_SNAPSHOT_DIR = tempfile.gettempdir()
_SNAPSHOT_PATH = os.path.join(_SNAPSHOT_DIR, "congine_snapshot.json")


class HttpContractRepository:
    """Fetch contracts from the control plane API with disk fallback."""

    def __init__(self, config: CongineConfig, logger: Optional[ILogger] = None) -> None:
        """Args:
        config: Runtime configuration (base URL, credentials, identifiers).
        logger: Optional structured logger for observability.
        """
        self.config = config
        self.logger = logger

    async def fetch_active_contracts(self) -> List[Dict]:
        """Fetch active contracts from the control plane.

        Returns:
            The ``contracts`` list from the control-plane response.

        Raises:
            httpx.HTTPError: On transport failure or non-2xx response.
            KeyError: If the response body omits the ``contracts`` key.
        """
        headers = {
            "X-API-Key": self.config.api_key or "",
            "X-Project-ID": self.config.project_id or "",
            "X-Tenant-ID": self.config.tenant_id or "",
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
        """Load contracts from the disk snapshot (stale-ok fallback).

        Returns:
            The persisted contracts list, or ``None`` if no readable snapshot
            exists.
        """
        try:
            with open(_SNAPSHOT_PATH, "r", encoding="utf-8") as fh:
                snapshot = json.load(fh)
            return snapshot.get("contracts")
        except FileNotFoundError, json.JSONDecodeError:
            return None

    def save_snapshot(self, contracts: List[Dict]) -> None:
        """Persist *contracts* to disk atomically.

        Writes to a temporary file in the snapshot directory and then performs
        an atomic :func:`os.replace`, ensuring readers never observe a partial
        file.

        Args:
            contracts: The contracts list to persist.
        """
        snapshot = {
            "version": "1.0",
            "contracts": contracts,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        os.makedirs(_SNAPSHOT_DIR, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=_SNAPSHOT_DIR, suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh)
            os.replace(temp_path, _SNAPSHOT_PATH)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
