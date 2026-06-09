"""PII-safe breach message sanitization (Layer 0).

Strips instance values that jsonschema and other validators embed in error
messages before they reach logs or telemetry (FIX-04).
"""

from __future__ import annotations

import re

# Strip quoted instance fragments conservatively (jsonschema style).
_QUOTED_VALUE_RE = re.compile(r"'[^']{1,500}'")


def sanitize_breach_message(message: str) -> str:
    """Return *message* with embedded instance values redacted.

    Conservative: replaces quoted substrings (typical jsonschema style) with
    ``'<redacted>'`` while preserving the constraint description.
    """
    if not message:
        return message
    sanitized = _QUOTED_VALUE_RE.sub("'<redacted>'", message)
    return sanitized
