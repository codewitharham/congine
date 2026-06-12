import pytest
from typing import Any, Dict
from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.adapters.guard import congine_guard


@pytest.fixture(autouse=True)
def _multi_tenant_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force multi-tenant mode + silence telemetry, scoped per-test.

    Set via monkeypatch rather than a module-level ``os.environ`` mutation so the
    change is reverted after each test and never leaks into sibling test modules
    (e.g. test_remediations.py's ``get_default()`` assertions).
    """
    monkeypatch.setenv("CONGINE_DEPLOYMENT_MODE", "multi_tenant")
    monkeypatch.setenv("CONGINE_TELEMETRY_ENABLED", "false")


# --- 1. PYTEST FIXTURES ---


@pytest.fixture(scope="module")
def contract_schema() -> Dict[str, Any]:
    """Provides a strict schema for an Agent Vendor Onboarding tool."""
    return {
        "type": "object",
        "properties": {
            "vendor_name": {"type": "string", "maxLength": 50},
            "corporate_email": {"type": "string", "format": "email"},
            "risk_score": {"type": "integer", "minimum": 1, "maximum": 100},
        },
        "required": ["vendor_name", "corporate_email", "risk_score"],
        "additionalProperties": False,
    }


@pytest.fixture(scope="function")
def tenant_alpha_container(contract_schema) -> ServiceContainer:
    """Bootstraps a clean container context for Tenant Alpha with keys seeded."""
    container = ServiceContainer.for_tenant(
        tenant_id="enterprise_alpha", project_id="vendor_management"
    )

    container.schema_storage.put(
        contract_id="vendor-onboarding-contract", schema=contract_schema
    )

    container.schema_storage.put(
        contract_id="vendor-onboarding-contract|latest", schema=contract_schema
    )

    return container


@pytest.fixture(scope="function")
def tenant_beta_container() -> ServiceContainer:
    """Bootstraps a separate container context for Tenant Beta (No contracts seeded)."""
    return ServiceContainer.for_tenant(tenant_id="corp_beta", project_id="purchasing")


# --- 2. THE CHOSEN AGENT TOOLS ---


def create_sync_agent_tool(container: ServiceContainer):
    @congine_guard(
        contract_id="vendor-onboarding-contract", version="latest", container=container
    )
    def sync_tool(llm_output: Dict[str, Any]) -> Dict[str, Any]:
        return llm_output

    return sync_tool


def create_async_agent_tool(container: ServiceContainer):
    @congine_guard(
        contract_id="vendor-onboarding-contract", version="latest", container=container
    )
    async def async_tool(llm_output: Dict[str, Any]) -> Dict[str, Any]:
        return llm_output

    return async_tool


# --- 3. ASSERTION TEST CASES ---


def test_agent_tool_happy_path(tenant_alpha_container):
    """Vector 00: Verify flawless execution and unwrapping of wrapped envelope structure."""
    sync_tool = create_sync_agent_tool(tenant_alpha_container)

    valid_generation = {
        "vendor_name": "Acme Logistics Corp",
        "corporate_email": "compliance@acmelogistics.com",
        "risk_score": 42,
    }

    wrapped_result = sync_tool(valid_generation)

    # Assert envelope structural signature
    assert "output" in wrapped_result
    assert "validation_result" in wrapped_result

    # Assert data mapping
    assert wrapped_result["output"]["vendor_name"] == "Acme Logistics Corp"
    assert wrapped_result["output"]["risk_score"] == 42


def test_agent_tool_contract_breach_and_pii_scrubbing(tenant_alpha_container):
    """Vector 02 & 03: Verify soft-failure capturing and PII error redaction."""
    sync_tool = create_sync_agent_tool(tenant_alpha_container)

    corrupted_generation = {
        "vendor_name": "Evil Corp Inc",
        "corporate_email": "not-an-email-address",  # Schema breach
        "risk_score": 999,  # Schema breach
        "secret_api_key": "sk_live_51NxLeakage",  # Extra property / PII leak
    }

    wrapped_result = sync_tool(corrupted_generation)

    # Under degrade policy, it returns a response envelope instead of throwing an error
    assert "validation_result" in wrapped_result

    # Convert validation metadata context to string to verify security filters
    validation_report_str = str(wrapped_result["validation_result"])

    # Core Security Safeguard Assertions:
    assert "sk_live_51NxLeakage" not in validation_report_str, (
        "CRITICAL: Raw PII leaked into validation report context!"
    )
    # Ensure the engine logged the breach properly
    assert (
        "breach" in validation_report_str.lower()
        or "fail" in validation_report_str.lower()
    )


@pytest.mark.asyncio
async def test_async_agent_tool_execution(tenant_alpha_container):
    """Vector 04/06: Ensure compiled async handlers correctly unwrap responses."""
    async_tool = create_async_agent_tool(tenant_alpha_container)

    valid_generation = {
        "vendor_name": "Globex Systems",
        "corporate_email": "security@globex.io",
        "risk_score": 12,
    }

    wrapped_result = await async_tool(valid_generation)
    assert wrapped_result["output"]["vendor_name"] == "Globex Systems"


def test_multi_tenant_strict_isolation(tenant_alpha_container, tenant_beta_container):
    """Vector 05: Assert that Tenant Beta cannot intercept or reuse Tenant Alpha's schema definitions."""
    alpha_tool = create_sync_agent_tool(tenant_alpha_container)
    beta_tool = create_sync_agent_tool(tenant_beta_container)

    payload = {
        "vendor_name": "Acme Logistics Corp",
        "corporate_email": "compliance@acmelogistics.com",
        "risk_score": 42,
    }

    # Tenant Alpha succeeds because their container cache has the contract
    wrapped_alpha = alpha_tool(payload)
    assert wrapped_alpha["output"]["vendor_name"] == "Acme Logistics Corp"

    # Tenant Beta must fail loudly because they do not have access to Alpha's memory block
    with pytest.raises(Exception) as exc_info:
        beta_tool(payload)

    assert "not found" in str(exc_info.value).lower()


def test_missing_container_in_multi_tenant_raises_loudly():
    """Vector 05-B: Guard against missing container references in multi-tenant mode."""

    @congine_guard(contract_id="any-contract", version="latest", container=None)
    def broken_tool(data):
        return data

    with pytest.raises(Exception) as exc_info:
        broken_tool({"test": "data"})

    assert "disabled in multi_tenant mode" in str(exc_info.value)
