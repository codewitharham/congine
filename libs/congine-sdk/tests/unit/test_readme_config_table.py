"""The README config table must stay in step with ``CongineConfig`` (audit Q7).

``.claude/CLAUDE.md`` designates that table "the canonical, user-facing config
doc" and the fourth touch of the mandatory 4-touch config change. It had drifted
to documenting 27 of 46 fields — including the standalone switch, the telemetry
kill-switch and the fail-closed JSON Schema dialect — while its own preamble
asserted every field was settable.

Filling it in once fixes today; these tests are what stop it drifting again. They
fail in all three directions: a field with no row, a row for a field that no
longer exists, and a row naming the wrong environment variable.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from congine_core.config import CongineConfig

_README = Path(__file__).resolve().parents[2] / "README.md"
_SECTION_HEADING = "## Configuration reference"
#: ``| `field` | `CONGINE_VAR` | default | description |``
_ROW = re.compile(r"^\|\s*`(?P<field>\w+)`\s*\|\s*`(?P<env>CONGINE_\w+)`\s*\|")


def _documented_rows() -> dict[str, str]:
    """Return ``{field_name: env_var}`` parsed from the README table."""
    text = _README.read_text(encoding="utf-8")
    start = text.index(_SECTION_HEADING)
    end = text.index("\n---\n", start)
    rows: dict[str, str] = {}
    for line in text[start:end].splitlines():
        match = _ROW.match(line)
        if match:
            rows[match.group("field")] = match.group("env")
    return rows


def _declared_fields() -> set[str]:
    return {f.name for f in dataclasses.fields(CongineConfig)}


def test_readme_exists_and_has_a_config_table() -> None:
    assert _README.is_file(), _README
    assert len(_documented_rows()) > 0, "config-reference table not found or unparsable"


def test_every_config_field_is_documented() -> None:
    """A field with no README row is a knob users cannot discover."""
    missing = sorted(_declared_fields() - set(_documented_rows()))
    assert not missing, (
        f"{len(missing)} CongineConfig field(s) missing from the README config "
        f"table: {missing}. Add a row for each (field, env var, default, "
        f"description)."
    )


def test_readme_documents_no_field_that_does_not_exist() -> None:
    """A row for a removed field is worse than no row — it is a false promise."""
    stale = sorted(set(_documented_rows()) - _declared_fields())
    assert not stale, (
        f"README config table documents field(s) that no longer exist on "
        f"CongineConfig: {stale}."
    )


def test_documented_env_vars_are_the_ones_from_env_reads() -> None:
    """Every documented ``CONGINE_*`` name must be one ``from_env()`` actually reads.

    Catches the subtler drift: a row that exists but points the user at a
    variable the loader ignores.
    """
    source = (
        Path(__file__).resolve().parents[2] / "src" / "congine_core" / "config.py"
    ).read_text(encoding="utf-8")
    read_by_loader = set(re.findall(r'"(CONGINE_\w+)"', source))

    wrong = {
        field: env
        for field, env in _documented_rows().items()
        if env not in read_by_loader
    }
    assert not wrong, (
        f"README documents environment variable(s) that config.py never reads: {wrong}."
    )


@pytest.mark.parametrize(
    "field, env",
    sorted(_documented_rows().items()),
)
def test_documented_field_env_pair_round_trips(field: str, env: str) -> None:
    """Each documented pair must actually be wired together in ``from_env()``.

    Asserts the env var appears in the same ``from_env`` assignment as the field
    it claims to set, so swapping two rows' variables is caught.
    """
    source = (
        Path(__file__).resolve().parents[2] / "src" / "congine_core" / "config.py"
    ).read_text(encoding="utf-8")

    # Match `field=<...>` up to the next keyword argument in the constructor call.
    assignment = re.search(
        rf"\n\s+{re.escape(field)}=(.*?)(?=\n\s+\w+=|\n\s*\)\n)",
        source,
        re.DOTALL,
    )
    assert assignment is not None, f"no from_env() assignment found for {field!r}"
    expression = assignment.group(1).strip().rstrip(",")

    resolved, trail = _resolve_env_reads(expression, source)
    assert env in resolved, (
        f"README says {field!r} is set by {env!r}, but from_env() resolves it "
        f"via {' -> '.join(trail)} to {sorted(resolved)}"
    )


def _resolve_env_reads(expression: str, source: str) -> tuple[set[str], list[str]]:
    """Resolve an assignment expression to the ``CONGINE_*`` names it can reach.

    Follows two kinds of indirection so the test does not need a special case per
    field: a bare local (the enum fields are parsed into one first) and a
    ``cls.<helper>()`` call (``base_url`` and ``deployment_mode`` both go through
    one). Bounded to a few hops — this is a documentation guard, not a compiler.
    """
    trail = [expression]
    for _ in range(4):
        found = set(re.findall(r'"(CONGINE_\w+)"', expression))
        if found:
            return found, trail

        bare_local = re.fullmatch(r"\w+", expression)
        helper_call = re.fullmatch(r"cls\.(\w+)\(.*\)", expression)

        if bare_local:
            match = re.search(
                rf"\n\s+{re.escape(expression)} = (.*?)(?=\n\s+\w+ =|\n\s+config = )",
                source,
                re.DOTALL,
            )
        elif helper_call:
            # Body of the named @classmethod/@staticmethod, up to the next def.
            match = re.search(
                rf"def {re.escape(helper_call.group(1))}\(.*?\n(.*?)(?=\n    @|\n    def )",
                source,
                re.DOTALL,
            )
        else:
            break

        if match is None:
            break
        expression = match.group(1).strip().rstrip(",")
        trail.append(expression.splitlines()[0][:60])

    return set(re.findall(r'"(CONGINE_\w+)"', expression)), trail
