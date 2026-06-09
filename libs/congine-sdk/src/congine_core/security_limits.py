"""Shared security limit constants (Layer 0).

Centralised bounds referenced by the rule engine, semantic validator, and
use-case input guards. Lives at L0 so every layer can import without violating
hexagonal boundaries.
"""

from __future__ import annotations

# ReDoS guard (audit H3) — schema-supplied regex patterns are untrusted input.
MAX_PATTERN_LENGTH = 1000
MAX_REGEX_VALUE_LENGTH = 50_000

# Input bounding (FIX-06).
DEFAULT_MAX_PAYLOAD_BYTES = 1_048_576
DEFAULT_MAX_SCHEMA_BYTES = 1_048_576
DEFAULT_MAX_CONTRACT_FILES = 1000
DEFAULT_MAX_STREAM_BUFFER_CHARS = 500_000
DEFAULT_MAX_HTTP_RESPONSE_BYTES = 10_485_760

# Semantic validation bounding (FIX-03).
DEFAULT_SEMANTIC_MAX_BREACHES = 100

__all__ = [
    "MAX_PATTERN_LENGTH",
    "MAX_REGEX_VALUE_LENGTH",
    "DEFAULT_MAX_PAYLOAD_BYTES",
    "DEFAULT_MAX_SCHEMA_BYTES",
    "DEFAULT_MAX_CONTRACT_FILES",
    "DEFAULT_MAX_STREAM_BUFFER_CHARS",
    "DEFAULT_MAX_HTTP_RESPONSE_BYTES",
    "DEFAULT_SEMANTIC_MAX_BREACHES",
]
