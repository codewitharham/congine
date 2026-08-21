from pathlib import Path

import pytest

from tools.check_architecture import check_architecture


SDK_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = SDK_ROOT / "src" / "congine_core"

#: One representative module per layer, used to build synthetic edge fixtures.
_LAYER_MODULE = {
    0: "congine_core.config",
    1: "congine_core.ports.logger",
    2: "congine_core.domain.models",
    3: "congine_core.usecases.sync",
    4: "congine_core.infrastructure.cache",
    5: "congine_core.adapters.guard",
}

#: One source file path per layer.
_LAYER_SOURCE = {
    0: "kernel_module.py",
    1: "ports/probe.py",
    2: "domain/probe.py",
    3: "usecases/probe.py",
    4: "infrastructure/probe.py",
    5: "adapters/probe.py",
}

#: The full CONGINE layer dependency matrix, asserted edge by edge.
#:
#: The four rows that matter most are the L4 rejections. A rule of the form
#: ``target <= source`` would wrongly admit ``L4 -> L2`` and ``L4 -> L3``,
#: which is exactly the defect this table exists to prevent from returning.
_MATRIX_CASES = [
    (0, 0, True),
    (0, 1, False),
    (0, 2, False),
    (0, 3, False),
    (0, 4, False),
    (0, 5, False),
    (1, 0, True),
    (1, 1, True),
    (1, 2, False),
    (1, 3, False),
    (1, 4, False),
    (1, 5, False),
    (2, 0, True),
    (2, 1, True),
    (2, 2, True),
    (2, 3, False),
    (2, 4, False),
    (2, 5, False),
    (3, 0, True),
    (3, 1, True),
    (3, 2, True),
    (3, 3, True),
    (3, 4, False),
    (3, 5, False),
    (4, 0, True),
    (4, 1, True),
    (4, 2, False),  # infrastructure must not reach into domain
    (4, 3, False),  # infrastructure must not reach into use cases
    (4, 4, True),
    (4, 5, False),
    (5, 0, True),
    (5, 1, True),
    (5, 2, True),
    (5, 3, True),
    (5, 4, True),
    (5, 5, True),
]


def _write_source(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _edge_violations(
    tmp_path: Path, source_layer: int, target_layer: int, *, type_checking: bool
) -> list:
    """Build a single-edge fixture and return whatever the checker reports."""
    root = tmp_path / "congine_core"
    import_line = f"from {_LAYER_MODULE[target_layer]} import Thing\n"
    if type_checking:
        body = f"from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    {import_line}"
    else:
        body = import_line
    _write_source(root, _LAYER_SOURCE[source_layer], body)
    return check_architecture(root)


def test_current_source_obeys_the_layer_matrix() -> None:
    assert check_architecture(SOURCE_ROOT) == []


@pytest.mark.parametrize(("source_layer", "target_layer", "allowed"), _MATRIX_CASES)
def test_runtime_edge_matches_layer_matrix(
    tmp_path: Path, source_layer: int, target_layer: int, allowed: bool
) -> None:
    violations = _edge_violations(
        tmp_path, source_layer, target_layer, type_checking=False
    )

    if allowed:
        assert violations == []
        return
    assert len(violations) == 1
    assert violations[0].source_layer == source_layer
    assert violations[0].target_layer == target_layer
    assert violations[0].type_checking is False


@pytest.mark.parametrize(("source_layer", "target_layer", "allowed"), _MATRIX_CASES)
def test_type_checking_edge_matches_the_same_layer_matrix(
    tmp_path: Path, source_layer: int, target_layer: int, allowed: bool
) -> None:
    """An erased import is still an architectural dependency (P1 policy).

    A module that needs the concrete type of an outer implementation knows
    about that implementation whether or not the import survives to runtime,
    so ``TYPE_CHECKING`` edges are judged by the identical matrix. There is no
    exemption and no allowlist.
    """
    violations = _edge_violations(
        tmp_path, source_layer, target_layer, type_checking=True
    )

    if allowed:
        assert violations == []
        return
    assert len(violations) == 1
    assert violations[0].source_layer == source_layer
    assert violations[0].target_layer == target_layer
    assert violations[0].type_checking is True


def test_infrastructure_may_use_kernel_and_ports_together(tmp_path: Path) -> None:
    """The allowed L4 shape: kernel and the ports it implements, nothing else."""
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "infrastructure/worker.py",
        "from congine_core.infrastructure.cache import Cache\n"
        "from congine_core.ports.logger import Logger\n"
        "from congine_core.ports.sync_runner import ISyncRunner\n"
        "from congine_core.models import Result\n"
        "from congine_core.config import Config\n",
    )

    assert check_architecture(root) == []


def test_infrastructure_cannot_reach_domain_through_the_compatibility_shim(
    tmp_path: Path,
) -> None:
    """``congine_core.domain.models`` keeps its L2 identity for the gate.

    The shim exists so the historical import path keeps working for callers,
    not so inner layers can launder an L2 dependency. Importing the canonical
    value contracts from an L4 module must name ``congine_core.models``.
    """
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "infrastructure/worker.py",
        "from congine_core.domain.models import Result\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].target_module == "congine_core.domain.models"
    assert violations[0].target_layer == 2


def test_kernel_models_are_importable_from_every_layer(tmp_path: Path) -> None:
    """The L0 placement is what makes the strict matrix satisfiable."""
    root = tmp_path / "congine_core"
    for layer, relative_path in _LAYER_SOURCE.items():
        _write_source(
            root,
            relative_path,
            f"# layer {layer}\nfrom congine_core.models import Result\n",
        )

    assert check_architecture(root) == []


def test_unimported_type_checking_name_does_not_hide_runtime_edge(
    tmp_path: Path,
) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "TYPE_CHECKING = True\n"
        "if TYPE_CHECKING:\n"
        "    from congine_core.infrastructure.worker import Worker\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].target_module == "congine_core.infrastructure.worker"


def test_rebound_type_checking_import_does_not_hide_runtime_edge(
    tmp_path: Path,
) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "from typing import TYPE_CHECKING\n"
        "TYPE_CHECKING = True\n"
        "if TYPE_CHECKING:\n"
        "    from congine_core.infrastructure.worker import Worker\n",
    )

    assert len(check_architecture(root)) == 1


def test_function_local_type_checking_shadow_does_not_hide_runtime_edge(
    tmp_path: Path,
) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "from typing import TYPE_CHECKING\n"
        "def run():\n"
        "    TYPE_CHECKING = True\n"
        "    if TYPE_CHECKING:\n"
        "        from congine_core.infrastructure.worker import Worker\n",
    )

    assert len(check_architecture(root)) == 1


def test_function_local_type_checking_import_is_still_enforced(
    tmp_path: Path,
) -> None:
    """Burying a ``TYPE_CHECKING`` guard inside a function changes nothing.

    The guard is resolved correctly at function scope — that machinery is
    covered by the shadowing tests below — but resolving it only decides how
    the edge is *labelled*, never whether it is judged.
    """
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "def run():\n"
        "    from typing import TYPE_CHECKING\n"
        "    if TYPE_CHECKING:\n"
        "        from congine_core.infrastructure.worker import Worker\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].target_module == "congine_core.infrastructure.worker"
    assert violations[0].type_checking is True


def test_method_does_not_resolve_type_checking_from_class_scope(
    tmp_path: Path,
) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "TYPE_CHECKING = True\n"
        "class Workflow:\n"
        "    from typing import TYPE_CHECKING\n"
        "    def run(self):\n"
        "        if TYPE_CHECKING:\n"
        "            from congine_core.infrastructure.worker import Worker\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].target_module == "congine_core.infrastructure.worker"


def test_nested_class_does_not_resolve_outer_class_type_checking(
    tmp_path: Path,
) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "TYPE_CHECKING = True\n"
        "class Outer:\n"
        "    from typing import TYPE_CHECKING\n"
        "    class Inner:\n"
        "        if TYPE_CHECKING:\n"
        "            from congine_core.infrastructure.worker import Worker\n",
    )

    assert len(check_architecture(root)) == 1


def test_cross_category_alias_is_not_trusted_as_type_checking(
    tmp_path: Path,
) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "from typing import TYPE_CHECKING as flag\n"
        "from importlib import import_module as flag\n"
        "if flag:\n"
        "    from congine_core.infrastructure.worker import Worker\n",
    )

    assert len(check_architecture(root)) == 1


def test_cross_category_alias_remains_a_possible_dynamic_import(
    tmp_path: Path,
) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "from typing import TYPE_CHECKING as load\n"
        "from importlib import import_module as load\n"
        "load('congine_core.infrastructure.worker')\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].target_module == "congine_core.infrastructure.worker"


def test_literal_dynamic_outward_imports_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "import importlib as loader\n"
        "from importlib import import_module as load\n"
        "loader.import_module('congine_core.infrastructure.worker')\n"
        "load('congine_core.adapters.guard')\n"
        "__import__('congine_core.infrastructure.cache')\n",
    )

    violations = check_architecture(root)

    assert [violation.target_layer for violation in violations] == [4, 5, 4]


def test_function_local_dynamic_import_alias_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "def run():\n"
        "    from importlib import import_module as load\n"
        "    load('congine_core.infrastructure.worker')\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].target_module == "congine_core.infrastructure.worker"


def test_runtime_l3_to_l4_import_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "from congine_core.infrastructure.worker import Worker\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].source_layer == 3
    assert violations[0].target_layer == 4
    assert violations[0].target_module == "congine_core.infrastructure.worker"


def test_runtime_l0_to_l2_import_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "config.py",
        "from congine_core.domain.models import Result\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].source_layer == 0
    assert violations[0].target_layer == 2
    assert violations[0].target_module == "congine_core.domain.models"


def test_internal_runtime_import_through_public_aggregator_is_rejected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "usecases/workflow.py",
        "from congine_core import ServiceContainer\n",
    )

    violations = check_architecture(root)

    assert len(violations) == 1
    assert violations[0].source_layer == 3
    assert violations[0].target_layer == 6
    assert violations[0].target_module == "congine_core"


def test_public_package_aggregator_is_exempt(tmp_path: Path) -> None:
    root = tmp_path / "congine_core"
    _write_source(
        root,
        "__init__.py",
        "from congine_core.adapters.guard import congine_guard\n",
    )

    assert check_architecture(root) == []
