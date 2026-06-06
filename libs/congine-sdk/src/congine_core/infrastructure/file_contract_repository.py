"""File-based contract repository (Layer 4).

:class:`FileContractRepository` implements
:class:`congine_core.ports.contract_repository.IContractRepository` by reading
contract JSON (and optionally YAML, when ``PyYAML`` is importable) from a
local directory. This is the **local-first / GitOps** entry-point promised in
the AMCE positioning: commit contracts into a repository, mount that directory
into the application, and the SDK reads them at boot without ever touching a
remote control plane.

The repository never raises across the protocol surface (the use case treats
it as offline-safe); failures degrade to an empty contract list.

Snapshot persistence is a no-op for this implementation — the file source is
itself the canonical snapshot — so :meth:`save_snapshot` is intentionally
silent and :meth:`load_snapshot` returns ``None`` (causing the use case to
re-read from the directory the next boot).
"""

from __future__ import annotations

import glob
import json
import os
from typing import Dict, List, Optional

from congine_core.ports.logger import ILogger


class FileContractRepository:
    """Read contracts from a local directory; no network or snapshot persistence."""

    def __init__(self, contracts_dir: str, logger: Optional[ILogger] = None) -> None:
        """Args:
        contracts_dir: Path to a directory containing ``*.json`` (and optionally
            ``*.yaml``/``*.yml``) contract files. Each file must contain either
            a single contract object or a ``contracts`` envelope.
        logger: Optional :class:`ILogger` for warnings on malformed files.
        """
        self.contracts_dir = contracts_dir
        self.logger = logger

    async def fetch_active_contracts(self) -> List[Dict]:
        """Return every well-formed contract found under :attr:`contracts_dir`.

        The method is declared ``async`` to satisfy the
        :class:`IContractRepository` protocol but does no I/O concurrency —
        directory reads are cheap and bounded by repository size.
        """
        if not self.contracts_dir or not os.path.isdir(self.contracts_dir):
            if self.logger is not None:
                self.logger.warning(
                    "Contracts directory missing",
                    contracts_dir=self.contracts_dir,
                )
            return []

        contracts: List[Dict] = []
        json_files = sorted(
            glob.glob(os.path.join(self.contracts_dir, "**", "*.json"), recursive=True)
        )
        for path in json_files:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                if self.logger is not None:
                    self.logger.warning(
                        "Skipping malformed contract file",
                        path=path,
                        error=str(exc),
                    )
                continue
            contracts.extend(self._extract(payload))

        # YAML is optional: only enumerate yaml files if PyYAML is importable.
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError:
            yaml = None  # type: ignore[assignment]
        if yaml is not None:
            yaml_files = sorted(
                glob.glob(
                    os.path.join(self.contracts_dir, "**", "*.yml"),
                    recursive=True,
                )
                + glob.glob(
                    os.path.join(self.contracts_dir, "**", "*.yaml"),
                    recursive=True,
                )
            )
            for path in yaml_files:
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        payload = yaml.safe_load(fh)
                except (OSError, yaml.YAMLError) as exc:  # type: ignore[attr-defined]
                    if self.logger is not None:
                        self.logger.warning(
                            "Skipping malformed contract file",
                            path=path,
                            error=str(exc),
                        )
                    continue
                contracts.extend(self._extract(payload))

        if self.logger is not None:
            self.logger.info(
                "Loaded contracts from directory",
                count=len(contracts),
                contracts_dir=self.contracts_dir,
            )
        return contracts

    def load_snapshot(self) -> Optional[List[Dict]]:
        """File source is the snapshot — return ``None`` to force re-read."""
        return None

    def save_snapshot(self, contracts: List[Dict]) -> None:
        """No-op: the file source is itself canonical."""
        if self.logger is not None:
            self.logger.debug(
                "save_snapshot is a no-op for FileContractRepository",
                count=len(contracts),
            )

    @staticmethod
    def _extract(payload: object) -> List[Dict]:
        """Normalise a parsed payload into a list of contract mappings.

        Accepts either a single contract object (``{"id": ..., "schema": ...}``)
        or a wrapping envelope (``{"contracts": [{...}, {...}]}``).
        """
        if isinstance(payload, dict):
            inner = payload.get("contracts")
            if isinstance(inner, list):
                return [c for c in inner if isinstance(c, dict)]
            if "id" in payload and "schema" in payload:
                return [payload]
            return []
        if isinstance(payload, list):
            return [c for c in payload if isinstance(c, dict)]
        return []
