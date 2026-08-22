"""Deterministic semantic-capability witnesses (P1.5 Slice A0, made repeatable).

Each witness answers one question about the *live evaluator*, not about what the
documentation believes: **does the evaluator actually enforce what contract
admission claims it enforces?** A mismatch is a G12 violation — admission
advertising policy-activation truth it cannot deliver.

These are functional pass/fail facts, so unlike the benchmark corpus they are
stable enough to gate on. Every witness runs against every configured draft.

Network safety: the external-reference witnesses run against a **local**
``http.server`` bound to ``127.0.0.1`` on an ephemeral port. Nothing here
contacts the public internet, and observing a hit on that local server is what
proves retrieval occurred.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from jsonschema import (
    Draft4Validator,
    Draft6Validator,
    Draft7Validator,
    Draft201909Validator,
    Draft202012Validator,
)
from jsonschema.protocols import Validator

#: Every draft CONGINE's ``jsonschema_draft`` config can select.
DRAFTS: Dict[str, type[Validator]] = {
    "draft4": Draft4Validator,
    "draft6": Draft6Validator,
    "draft7": Draft7Validator,
    "draft201909": Draft201909Validator,
    "draft202012": Draft202012Validator,
}


@dataclass(frozen=True)
class Witness:
    """One capability question and its observed answer."""

    name: str
    draft: str
    enforced: bool
    outcome: str
    detail: str = ""
    retrieval_observed: bool = False


@dataclass
class _Recorder:
    hits: List[str] = field(default_factory=list)


def _evaluate(
    cls: type[Validator],
    schema: Dict[str, Any],
    payload: Dict[str, Any],
    registry: Any = None,
) -> Tuple[bool, str, str]:
    """Return ``(enforced, outcome, detail)`` for one evaluation."""
    try:
        kwargs = {"registry": registry} if registry is not None else {}
        errors = list(cls(schema, **kwargs).iter_errors(payload))
    except RecursionError:
        return False, "error", "RecursionError"
    except Exception as exc:  # noqa: BLE001 - classification is the point
        return False, "error", type(exc).__name__
    if errors:
        return True, "enforced", f"{len(errors)} breach(es)"
    return False, "silent-pass", "no breach reported"


def _obj(spec: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "properties": {"f": spec}}


#: ``name -> (schema, non-conforming payload)``. Each payload *violates* the
#: clause under test, so "no breach" means the clause is not enforced.
LOCAL_CASES: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {
    "pattern": (_obj({"type": "string", "pattern": "^[0-9]+$"}), {"f": "abc"}),
    "patternProperties": (
        {"type": "object", "patternProperties": {"^n_": {"type": "number"}}},
        {"n_x": "not-a-number"},
    ),
    "contentEncoding": (
        _obj({"type": "string", "contentEncoding": "base64"}),
        {"f": "!!!not-base64!!!"},
    ),
    "contentMediaType": (
        _obj({"type": "string", "contentMediaType": "application/json"}),
        {"f": "not json"},
    ),
    "unknown-keyword": (_obj({"type": "string", "xUnknown": 5}), {"f": "zz"}),
    "ref-local-valid": (
        {
            "type": "object",
            "$defs": {"S": {"type": "number"}},
            "properties": {"f": {"$ref": "#/$defs/S"}},
        },
        {"f": "string-not-number"},
    ),
    "ref-local-missing": (
        {"type": "object", "properties": {"f": {"$ref": "#/$defs/ABSENT"}}},
        {"f": "anything"},
    ),
    "ref-local-cyclic": (
        {
            "type": "object",
            "$defs": {"A": {"$ref": "#/$defs/A"}},
            "properties": {"f": {"$ref": "#/$defs/A"}},
        },
        {"f": "anything"},
    ),
}

#: format name -> payload that violates it.
FORMAT_CASES: Dict[str, str] = {"email": "not-an-email", "unknown-xyz": "anything"}


def run_local_witnesses() -> List[Witness]:
    """Run every non-network witness against every draft."""
    out: List[Witness] = []
    for draft, cls in DRAFTS.items():
        for name, (schema, payload) in LOCAL_CASES.items():
            enforced, outcome, detail = _evaluate(cls, schema, payload)
            out.append(Witness(name, draft, enforced, outcome, detail))
        for fmt, bad in FORMAT_CASES.items():
            schema = _obj({"type": "string", "format": fmt})
            checker = getattr(cls, "FORMAT_CHECKER", None)
            for policy, active in (("format-off", None), ("format-on", checker)):
                try:
                    errors = list(
                        cls(schema, format_checker=active).iter_errors({"f": bad})
                    )
                    enforced = bool(errors)
                    outcome = "enforced" if enforced else "silent-pass"
                    detail = f"{len(errors)} breach(es)"
                except Exception as exc:  # noqa: BLE001
                    enforced, outcome, detail = False, "error", type(exc).__name__
                out.append(
                    Witness(f"format[{fmt}]/{policy}", draft, enforced, outcome, detail)
                )
    return out


def _local_server(recorder: _Recorder) -> Tuple[socketserver.TCPServer, str]:
    """Start a loopback server that records every request it receives."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            recorder.hits.append(self.path)
            body = json.dumps({"type": "number"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: Any) -> None:
            return

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/remote.json"


def run_retrieval_witnesses(
    registry_factory: Optional[Callable[[], Any]] = None,
) -> List[Witness]:
    """Ask whether an external ``$ref`` causes a real fetch.

    A hit on the loopback server is direct proof of retrieval — the decisive
    evidence, because interception at the socket layer produced a false negative
    during A0 while ``urlopen`` was in fact being called.

    Args:
        registry_factory: Builds the registry passed to the validator. ``None``
            measures current default behaviour; supplying a no-retrieval registry
            measures the proposed fix.
    """
    recorder = _Recorder()
    server, url = _local_server(recorder)
    out: List[Witness] = []
    try:
        for draft, cls in DRAFTS.items():
            before = len(recorder.hits)
            schema = {"type": "object", "properties": {"f": {"$ref": url}}}
            registry = registry_factory() if registry_factory else None
            enforced, outcome, detail = _evaluate(
                cls, schema, {"f": "string-not-number"}, registry
            )
            fetched = len(recorder.hits) > before
            out.append(
                Witness(
                    "ref-external-http",
                    draft,
                    enforced,
                    outcome,
                    detail,
                    retrieval_observed=fetched,
                )
            )
    finally:
        server.shutdown()
        server.server_close()
    return out


def summarize(witnesses: List[Witness]) -> Dict[str, Any]:
    """Collapse per-draft witnesses into one row per capability.

    Reports agreement explicitly: a capability that behaves differently across
    drafts is itself a finding, so it is never averaged away.
    """
    by_name: Dict[str, List[Witness]] = {}
    for wit in witnesses:
        by_name.setdefault(wit.name, []).append(wit)
    rows: Dict[str, Any] = {}
    for name, group in by_name.items():
        outcomes = sorted({w.outcome for w in group})
        rows[name] = {
            "drafts": len(group),
            "all_agree": len(outcomes) == 1,
            "outcomes": outcomes,
            "enforced_on": sorted(w.draft for w in group if w.enforced),
            "retrieval_observed": any(w.retrieval_observed for w in group),
        }
    return rows


# --------------------------------------------------------------------------- #
# A0.1 — dialect-specific capability truth
# --------------------------------------------------------------------------- #

#: ``keyword -> (schema, payload that violates it)``. Every case is a black-box
#: witness: "no breach" means the configured draft does not enforce the keyword,
#: whatever admission believes.
DIALECT_CASES: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {
    "const": ({"type": "object", "properties": {"f": {"const": "X"}}}, {"f": "WRONG"}),
    "if": (
        {
            "type": "object",
            "properties": {"f": {"type": "string"}},
            "if": {"properties": {"f": {"const": "a"}}},
            "then": {"required": ["must"]},
        },
        {"f": "a"},
    ),
    "contains": (
        {
            "type": "object",
            "properties": {"f": {"type": "array", "contains": {"type": "number"}}},
        },
        {"f": ["s", "t"]},
    ),
    "minContains": (
        {
            "type": "object",
            "properties": {
                "f": {"type": "array", "contains": {"type": "number"}, "minContains": 2}
            },
        },
        {"f": [1, "s"]},
    ),
    "maxContains": (
        {
            "type": "object",
            "properties": {
                "f": {"type": "array", "contains": {"type": "number"}, "maxContains": 1}
            },
        },
        {"f": [1, 2, 3]},
    ),
    "dependentRequired": (
        {"type": "object", "dependentRequired": {"a": ["b"]}},
        {"a": 1},
    ),
    "dependentSchemas": (
        {"type": "object", "dependentSchemas": {"a": {"required": ["b"]}}},
        {"a": 1},
    ),
    "prefixItems": (
        {
            "type": "object",
            "properties": {"f": {"type": "array", "prefixItems": [{"type": "number"}]}},
        },
        {"f": ["not-number"]},
    ),
    "propertyNames": (
        {"type": "object", "propertyNames": {"pattern": "^a"}},
        {"zzz": 1},
    ),
    "exclusiveMinimum": (
        {
            "type": "object",
            "properties": {"f": {"type": "number", "exclusiveMinimum": 5}},
        },
        {"f": 5},
    ),
    "exclusiveMaximum": (
        {
            "type": "object",
            "properties": {"f": {"type": "number", "exclusiveMaximum": 5}},
        },
        {"f": 5},
    ),
    "uniqueItems": (
        {"type": "object", "properties": {"f": {"type": "array", "uniqueItems": True}}},
        {"f": [1, 1]},
    ),
    "multipleOf": (
        {"type": "object", "properties": {"f": {"type": "number", "multipleOf": 3}}},
        {"f": 4},
    ),
    "additionalProperties": (
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "additionalProperties": False,
        },
        {"a": "x", "b": 1},
    ),
    "minLength": (
        {"type": "object", "properties": {"f": {"type": "string", "minLength": 5}}},
        {"f": "ab"},
    ),
    "maxItems": (
        {"type": "object", "properties": {"f": {"type": "array", "maxItems": 1}}},
        {"f": [1, 2]},
    ),
    "minProperties": ({"type": "object", "minProperties": 3}, {"a": 1}),
    "oneOf": (
        {
            "type": "object",
            "properties": {"f": {"oneOf": [{"type": "number"}, {"type": "boolean"}]}},
        },
        {"f": "string"},
    ),
    "not": (
        {"type": "object", "properties": {"f": {"not": {"type": "string"}}}},
        {"f": "string"},
    ),
}

#: Keywords implemented *inside* another keyword's handler rather than as their
#: own entry in ``VALIDATORS``. Deriving capability from handler presence alone
#: would therefore under-report them — measured, not assumed: ``then``/``else``
#: are enforced wherever ``if`` is, and ``minContains``/``maxContains`` are
#: enforced on 2019-09+ even though neither has a standalone handler.
COMPOSED_KEYWORDS: Dict[str, str] = {
    "then": "if",
    "else": "if",
    "minContains": "contains",
    "maxContains": "contains",
}

#: Container keywords that assert nothing on their own; ``$ref`` resolves into
#: them. Advertising them as enforced assertions is a category error.
CONTAINER_KEYWORDS = frozenset({"$defs", "definitions"})


def run_dialect_witnesses() -> List[Witness]:
    """Observe, per draft, which semantic keywords are genuinely enforced."""
    out: List[Witness] = []
    for draft, cls in DRAFTS.items():
        for keyword, (schema, payload) in DIALECT_CASES.items():
            enforced, outcome, detail = _evaluate(cls, schema, payload)
            out.append(Witness(f"kw:{keyword}", draft, enforced, outcome, detail))
    return out


def observed_capability(draft: str) -> Dict[str, bool]:
    """Return ``keyword -> enforced?`` as *observed* for one draft."""
    cls = DRAFTS[draft]
    result: Dict[str, bool] = {}
    for keyword, (schema, payload) in DIALECT_CASES.items():
        enforced, _, _ = _evaluate(cls, schema, payload)
        result[keyword] = enforced
    return result


def derived_capability(draft: str) -> Dict[str, bool]:
    """Return ``keyword -> enforced?`` *derived* from the validator class.

    Primary signal is ``VALIDATORS`` membership — the handlers the concrete
    class actually installs. Composed keywords follow their parent, because
    handler presence under-reports them.
    """
    cls = DRAFTS[draft]
    handlers = set(getattr(cls, "VALIDATORS", {}))
    result: Dict[str, bool] = {}
    for keyword in DIALECT_CASES:
        parent = COMPOSED_KEYWORDS.get(keyword)
        if parent is not None:
            result[keyword] = parent in handlers and _composed_supported(draft, keyword)
        else:
            result[keyword] = keyword in handlers
    return result


#: ``minContains``/``maxContains`` exist only from 2019-09 even though
#: ``contains`` is present from draft6. Measured, not inferred from the spec.
_COMPOSED_MIN_DRAFT = {"minContains": 3, "maxContains": 3}
_DRAFT_ORDER = {
    "draft4": 0,
    "draft6": 1,
    "draft7": 2,
    "draft201909": 3,
    "draft202012": 4,
}


def _composed_supported(draft: str, keyword: str) -> bool:
    floor = _COMPOSED_MIN_DRAFT.get(keyword)
    if floor is None:
        return True
    return _DRAFT_ORDER[draft] >= floor


def capability_drift() -> Dict[str, List[str]]:
    """Return per-draft keywords where derivation disagrees with observation.

    An empty result is what lets the derived capability model be trusted in
    production: it proves the model is not quietly diverging from what the
    evaluator actually does.
    """
    drift: Dict[str, List[str]] = {}
    for draft in DRAFTS:
        observed = observed_capability(draft)
        derived = derived_capability(draft)
        bad = sorted(k for k in observed if observed[k] != derived[k])
        if bad:
            drift[draft] = bad
    return drift


# --------------------------------------------------------------------------- #
# A.1 — hermetic retrieval witness
# --------------------------------------------------------------------------- #


@dataclass
class RetrieverSpy:
    """Counts every reference resolution the evaluator asks for.

    The loopback-server witness proved retrieval decisively during A0 and is
    kept as adversarial evidence, but binding a socket is a poor dependency for
    ordinary CI. This spy sits at the same boundary the fix uses — the
    ``referencing`` retriever — so it observes the identical event without a
    network stack.
    """

    calls: List[str] = field(default_factory=list)

    def __call__(self, uri: str) -> Any:
        self.calls.append(uri)
        from referencing.exceptions import NoSuchResource

        raise NoSuchResource(ref=uri)


def hermetic_retrieval_witness(uri: str) -> Dict[str, Any]:
    """Prove, without a socket, that a no-retrieval registry blocks external refs.

    Returns the observed outcome per draft plus the spy's call log. A call
    recorded here means the evaluator *wanted* to fetch: the registry refused
    it, which is exactly the defence-in-depth behaviour Slice B installs
    beneath admission.
    """
    from referencing import Registry

    results: Dict[str, Any] = {}
    for draft, cls in DRAFTS.items():
        spy = RetrieverSpy()
        registry = Registry(retrieve=spy)
        schema = {"type": "object", "properties": {"f": {"$ref": uri}}}
        enforced, outcome, detail = _evaluate(cls, schema, {"f": "x"}, registry)
        results[draft] = {
            "outcome": outcome,
            "detail": detail,
            "enforced": enforced,
            "retrieval_requested": len(spy.calls),
            "fetched": False,
        }
    return results


def hermetic_local_ref_witness() -> Dict[str, Any]:
    """A valid local JSON-pointer ref must still be enforced under the registry.

    Blocking retrieval is only correct if it costs no legitimate capability, so
    this is the other half of the no-retrieval proof.
    """
    from referencing import Registry

    results: Dict[str, Any] = {}
    schema = {
        "type": "object",
        "$defs": {"S": {"type": "number"}},
        "properties": {"f": {"$ref": "#/$defs/S"}},
    }
    for draft, cls in DRAFTS.items():
        spy = RetrieverSpy()
        enforced, outcome, detail = _evaluate(
            cls, schema, {"f": "not-a-number"}, Registry(retrieve=spy)
        )
        results[draft] = {
            "outcome": outcome,
            "enforced": enforced,
            "retrieval_requested": len(spy.calls),
        }
    return results
