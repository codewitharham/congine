"""PII-safe breach message sanitization (Layer 0).

Strips instance values that jsonschema and other validators embed in error
messages before they reach logs or telemetry (FIX-04).
"""

from __future__ import annotations

from typing import cast

import re2 as _re2  # type: ignore[import-untyped]


# RE2 deliberately excludes backreferences, guaranteeing linear-time matching
# even for attacker-controlled validator messages. Spell the two quote forms as
# separate alternatives to preserve the legacy sanitizer's output without the
# stdlib-regex ``(['\"])(.*?)\1`` backreference.
_STRONG_SANITIZATION_RE = _re2.compile(r'(?:".*?"|\'.*?\'|\b\d{4,}\b)')


def sanitize_breach_message(message: str) -> str:
    """Return *message* with embedded instance values redacted.

    Conservative: replaces quoted substrings (typical jsonschema style) with
    ``'<redacted>'`` while preserving the constraint description.
    """
    if not message:
        return message
    sanitized = _STRONG_SANITIZATION_RE.sub("'<redacted>'", message)
    return cast(str, sanitized)
