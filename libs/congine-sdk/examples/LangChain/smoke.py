"""Cross-platform, network-free smoke test for the shipped LangChain example."""

from __future__ import annotations

import os
from pathlib import Path


_EXAMPLE_DIR = Path(__file__).resolve().parent

# Set the complete offline posture before importing ``agent``: that module
# constructs and bootstraps its container at import time.
os.environ["CONGINE_LOCAL_CONTRACTS_DIR"] = str(_EXAMPLE_DIR / "contracts")
os.environ["CONGINE_SEMANTIC_VALIDATION"] = "true"
os.environ["CONGINE_TELEMETRY_ENABLED"] = "false"
os.environ["CONGINE_START_BACKGROUND_SERVICES"] = "false"
os.environ["CONGINE_BASE_URL"] = "http://localhost:8080"
os.environ["CONGINE_FAIL_MODE"] = "degrade"
os.environ["GOOGLE_API_KEY"] = ""

from agent import (  # noqa: E402
    container,
    process_untrusted_customer_ticket,
    stream_support_reply,
)


def main() -> None:
    """Exercise the provider-free fallback and the streamed reply end to end."""
    try:
        output = process_untrusted_customer_ticket(
            "TKT-0001", "Offline smoke test: return requested."
        )
        assert output["action"] == "escalate"
        assert output["confidence_score"] == 0.5

        # The callback path: tokens plus the matching final LLMResult.
        reply = stream_support_reply()
        assert reply is not None and reply.is_pass()
        print(
            "LangChain example smoke passed "
            "(offline fallback and streamed reply validated)."
        )
    finally:
        container.close()


if __name__ == "__main__":
    main()
