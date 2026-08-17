"""Adversarial tests for localhost host parsing (FIX-01)."""

from __future__ import annotations

import pytest

from congine_core.config import CongineConfig, CongineConfigurationError, Region


def _cfg(url: str) -> CongineConfig:
    """A *valid* config for an arbitrary URL, so locality can be tested in isolation.

    Credentials and ``allow_cleartext`` are supplied because construction now
    validates (they were previously omitted only because nothing checked). They
    are irrelevant to what these tests assert — :meth:`is_local_base_url` parses
    the hostname and consults neither.
    """
    return CongineConfig(
        base_url=url,
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.US,
        allow_cleartext=True,
    )


def test_notlocalhost_is_not_local() -> None:
    assert not _cfg("http://notlocalhost:8080").is_local_base_url()


def test_localhost_subdomain_is_not_local() -> None:
    assert not _cfg("http://localhost.evil.com:8080").is_local_base_url()


def test_real_localhost_is_local() -> None:
    assert _cfg("http://localhost:8080").is_local_base_url()


def test_loopback_ip_is_local() -> None:
    assert _cfg("http://127.0.0.1:8080").is_local_base_url()


def test_notlocalhost_requires_credentials_at_construction() -> None:
    """A non-local URL without credentials is rejected — now at construction.

    Behaviour change, and a strengthening. This previously built the invalid
    config successfully and only raised on a separate, explicit ``validate()``
    call — which is precisely the bypass the closeout removed: nothing forced a
    caller to make that call, so a directly constructed config skipped the
    credential and HTTPS policy entirely. Rejection now happens at construction,
    so the invalid config cannot exist at all.
    """
    with pytest.raises(CongineConfigurationError):
        CongineConfig(
            base_url="http://notlocalhost:8080",
            api_key=None,
            project_id=None,
            tenant_id=None,
            region=Region.US,
        )
