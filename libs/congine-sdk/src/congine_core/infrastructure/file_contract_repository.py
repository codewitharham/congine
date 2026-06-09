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
from typing import Any, Optional

from congine_core.ports.logger import ILogger


class FileContractRepository:
    """Read contracts from a local directory; no network or snapshot persistence."""

    def __init__(
        self,
        contracts_dir: str,
        logger: Optional[ILogger] = None,
        max_contract_files: int = 1000,
        max_file_bytes: int = 1_048_576,
    ) -> None:
        """Args:
        contracts_dir: Path to a directory containing ``*.json`` (and optionally
            ``*.yaml``/``*.yml``) contract files. Each file must contain either
            a single contract object or a ``contracts`` envelope.
        logger: Optional :class:`ILogger` for warnings on malformed files.
        max_contract_files: Stop scanning after this many files (FIX-06).
        max_file_bytes: Maximum bytes read per contract file.
        """
        self.contracts_dir = contracts_dir
        self.logger = logger
        self.max_contract_files = max_contract_files
        self.max_file_bytes = max_file_bytes

    async def fetch_active_contracts(self) -> list[dict[str, Any]]:
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

        contracts: list[dict[str, Any]] = []
        json_files = sorted(
            glob.glob(os.path.join(self.contracts_dir, "**", "*.json"), recursive=True)
        )[: self.max_contract_files]
        for path in json_files:
            try:
                payload = self._read_json_file(path)
            except (OSError, json.JSONDecodeError) as exc:
                if self.logger is not None:
                    self.logger.warning(
                        "Skipping malformed contract file",
                        path=path,
                        error_type=type(exc).__name__,
                    )
                continue
            contracts.extend(self._extract(payload))

        # YAML is optional: only enumerate yaml files if PyYAML is importable.
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            yaml = None
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
            )[: max(0, self.max_contract_files - len(json_files))]
            for path in yaml_files:
                try:
                    payload = self._read_yaml_file(path, yaml)
                except (OSError, yaml.YAMLError) as exc:
                    if self.logger is not None:
                        self.logger.warning(
                            "Skipping malformed contract file",
                            path=path,
                            error_type=type(exc).__name__,
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

    def load_snapshot(self) -> Optional[list[dict[str, Any]]]:
        """File source is the snapshot — return ``None`` to force re-read."""
        return None

    def save_snapshot(self, contracts: list[dict[str, Any]]) -> None:
        """No-op: the file source is itself canonical."""
        if self.logger is not None:
            self.logger.debug(
                "save_snapshot is a no-op for FileContractRepository",
                count=len(contracts),
            )

    def _read_json_file(self, path: str) -> object:
        with open(path, "rb") as fh:
            raw = fh.read(self.max_file_bytes + 1)
        if len(raw) > self.max_file_bytes:
            raise OSError(f"Contract file exceeds max_file_bytes: {path}")
        return json.loads(raw.decode("utf-8"))

    def _read_yaml_file(self, path: str, yaml: Any) -> object:
        with open(path, "rb") as fh:
            raw = fh.read(self.max_file_bytes + 1)
        if len(raw) > self.max_file_bytes:
            raise OSError(f"Contract file exceeds max_file_bytes: {path}")
        return yaml.safe_load(raw.decode("utf-8"))

    @staticmethod
    def _extract(payload: object) -> list[dict[str, Any]]:
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
