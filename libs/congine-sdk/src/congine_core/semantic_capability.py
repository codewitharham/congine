"""Semantic evaluator capability (Layer 0 kernel).

:class:`SemanticCapability` is the immutable answer to one question that
contract admission must ask before it may activate policy:

    *Given the evaluator stack this container actually wired, which semantic
    clauses will genuinely be enforced?*

**Why this exists (P1.5).** Admission previously composed its capability set
from a static keyword list whenever semantic validation was enabled, ignoring
which JSON Schema dialect was configured. Measured against every supported
validator, that advertised enforcement the evaluator did not have — 11 keywords
silently unenforced on draft4, 6 on draft6, 5 on draft7, 1 on 2019-09. Each was
a G12 violation: admission claiming policy-activation truth it could not
deliver.

Capability is therefore no longer assumed. It is **derived from the concrete
validator at composition time** (L5), described by this immutable value, and
passed inward to admission (L2). The derivation lives in L4 beside the evaluator
it describes; only the resulting value crosses layers, so no inner layer gains a
dependency on infrastructure.

**Why L0.** This type satisfies the kernel admission principle: pure data, no
behaviour that decides anything, standard-library imports only, no I/O, and
genuinely exchanged across L2/L4/L5. It is a vocabulary term, not a mechanism.

**P1.5 scope note.** ``allow_external_references`` exists to make the current
policy explicit and testable rather than implied by omission. P1.5 supports
**verified local JSON-pointer references only**; external retrieval is not a
supported contract capability, and the field is expected to stay ``False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet

__all__ = ["SemanticCapability"]


@dataclass(frozen=True)
class SemanticCapability:
    """What the wired semantic evaluator can actually enforce.

    Attributes:
        draft: Canonical dialect identifier the evaluator was built for. Recorded
            so a capability value can be traced back to the evaluator that
            produced it, and so a mismatch is visible rather than silent.
        enforced_keywords: Semantic keywords the concrete evaluator genuinely
            asserts on *this* dialect. Derived from the validator's own handler
            table plus measured composed-keyword behaviour — never from a
            hand-maintained per-draft list.
        format_assertion: Whether ``format`` is asserted at all. When ``False``
            the evaluator treats every ``format`` as an annotation, so no format
            name is enforceable regardless of how well known it is.
        supported_formats: Format names the configured checker can actually
            assert. Empty when :attr:`format_assertion` is ``False``. An
            unrecognised name is unenforceable even while format checking is on,
            which is why this is a name set rather than a boolean.
        allow_external_references: Whether ``$ref`` may resolve outside the
            document. **False throughout P1.5** — see the module docstring.
    """

    draft: str
    enforced_keywords: FrozenSet[str] = field(default_factory=frozenset)
    format_assertion: bool = False
    supported_formats: FrozenSet[str] = field(default_factory=frozenset)
    allow_external_references: bool = False

    def enforces(self, keyword: str) -> bool:
        """Return whether *keyword* is genuinely asserted by this evaluator."""
        return keyword in self.enforced_keywords

    def enforces_format(self, name: str) -> bool:
        """Return whether the concrete checker can assert format *name*.

        Both conditions matter and neither implies the other: format assertion
        may be enabled while a specific name has no checker, and a well-known
        name is still unenforceable when assertion is off.
        """
        return self.format_assertion and name in self.supported_formats

    @classmethod
    def native_only(cls) -> "SemanticCapability":
        """Capability when no semantic evaluator is wired.

        Distinct from an empty-but-configured capability: it records that the
        absence is by configuration, not a derivation failure.
        """
        return cls(draft="none")
