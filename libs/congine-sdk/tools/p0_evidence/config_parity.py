"""P0 configuration parity: direct construction must equal environment construction.

Invariant I-04. ``CongineConfig(...)`` and ``CongineConfig.from_env()`` are two
doors into the same object, and both must arrive at the same canonical state::

    CongineConfig(...) -> __post_init__ -> normalize -> validate

The defect this guards against is subtle and was real in P0: an environment
variable read as a raw string leaves an enum-typed field holding ``"strict"``
instead of ``FailMode.STRICT``. Both compare equal under ``==`` — the enums are
``str``-backed — so tests pass while production code branching on ``is``
identity silently takes the wrong path. For ``fail_mode`` that meant a strict
deployment degrading instead of raising: enforcement lost, silently.

So parity is asserted on **type identity**, not only equality. Comparing with
``==`` alone would reproduce the original blind spot.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List

from congine_core.config import CongineConfig
from tools.p0_evidence.report import EvidenceResult

#: Control-plane fields have no defaults on the direct constructor, so both
#: doors are fed the identical values. Otherwise this would compare two
#: different configurations and call the difference a parity failure.
BASE_ENV = {
    "CONGINE_BASE_URL": "https://control.example.test",
    "CONGINE_API_KEY": "evidence-key",
    "CONGINE_PROJECT_ID": "evidence-project",
    "CONGINE_TENANT_ID": "evidence-tenant",
}
BASE_KWARGS: Dict[str, Any] = {
    "base_url": BASE_ENV["CONGINE_BASE_URL"],
    "api_key": BASE_ENV["CONGINE_API_KEY"],
    "project_id": BASE_ENV["CONGINE_PROJECT_ID"],
    "tenant_id": BASE_ENV["CONGINE_TENANT_ID"],
    "region": "us",
}

#: (env var, env string, kwarg, directly-constructed value). The env strings use
#: mixed case on purpose: canonicalisation is part of the contract. ``fail_mode``
#: is the row that matters most — it is the one whose raw-string form silently
#: turned a strict deployment into a degrading one.
ENUM_ROWS = [
    ("CONGINE_FAIL_MODE", "STRICT", "fail_mode", "strict"),
    ("CONGINE_DEPLOYMENT_MODE", "multi_tenant", "deployment_mode", "multi_tenant"),
    ("CONGINE_CONTRACT_SOURCE", "File", "contract_source", "file"),
    ("CONGINE_CONTRACT_ADMISSION", "warn", "contract_admission", "warn"),
    ("CONGINE_REGION", "US", "region", "us"),
]


@contextmanager
def _environment(values: Dict[str, str]) -> Iterator[None]:
    """Run with exactly *values* overlaid on ``CONGINE_*``, then restore."""
    saved = {k: v for k, v in os.environ.items() if k.startswith("CONGINE_")}
    for key in saved:
        del os.environ[key]
    os.environ.update(values)
    try:
        yield
    finally:
        for key in [k for k in os.environ if k.startswith("CONGINE_")]:
            del os.environ[key]
        os.environ.update(saved)


def run() -> EvidenceResult:
    """Compare direct and environment construction field by field."""
    rows: Dict[str, Any] = {}
    failures: List[str] = []

    for env_var, env_value, kwarg, direct_value in ENUM_ROWS:
        direct = CongineConfig(**{**BASE_KWARGS, kwarg: direct_value})  # type: ignore[arg-type]
        with _environment({**BASE_ENV, env_var: env_value}):
            from_env = CongineConfig.from_env()

        direct_field = getattr(direct, kwarg)
        env_field = getattr(from_env, kwarg)

        same_value = direct_field == env_field
        # The decisive check: a raw string that merely compares equal is the
        # exact defect P0 closed, so identity of type must match too.
        same_type = type(direct_field) is type(env_field)
        canonical = not isinstance(env_field, str) or type(env_field) is not str

        if same_value and same_type and canonical:
            rows[kwarg] = f"OK  {env_field!r} ({type(env_field).__name__})"
        else:
            rows[kwarg] = (
                f"MISMATCH direct={direct_field!r}"
                f"({type(direct_field).__name__}) "
                f"env={env_field!r}({type(env_field).__name__})"
            )
            failures.append(kwarg)

    # Whole-object parity on an otherwise-default construction: no field may
    # diverge between the two doors.
    with _environment(dict(BASE_ENV)):
        env_default = CongineConfig.from_env()
    direct_default = CongineConfig(**BASE_KWARGS)  # type: ignore[arg-type]
    diverged = [
        name
        for name in vars(direct_default)
        if getattr(direct_default, name) != getattr(env_default, name)
    ]
    rows["default construction"] = (
        "OK  all fields agree" if not diverged else f"DIVERGED {diverged}"
    )
    failures.extend(diverged)

    return EvidenceResult(
        name="Configuration parity",
        passed=not failures,
        headline=(
            f"{len(ENUM_ROWS)}/{len(ENUM_ROWS)} enum fields canonical and "
            f"{'identical' if not diverged else 'DIVERGENT'} under both doors"
        ),
        details=rows,
    )
