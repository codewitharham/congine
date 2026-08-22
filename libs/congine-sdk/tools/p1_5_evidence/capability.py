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
