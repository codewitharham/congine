"""Enforce Congine's layer dependency matrix.

The checker intentionally uses only the Python standard library so the
architecture gate does not depend on the package it is checking.

**The rule is a matrix, not an ordering.** An earlier revision approved an edge
whenever the target layer's number was less than or equal to the source's. That
is wrong for L4: infrastructure implements capabilities *declared by ports*, and
does not earn the right to depend on domain or use cases merely because they are
numerically inward. ``L4 -> L2`` and ``L4 -> L3`` are forbidden even though
``2 < 4`` and ``3 < 4``. See :data:`_ALLOWED_DEPENDENCIES`.

**``TYPE_CHECKING`` imports are enforced, not exempt.** An internal import under
``if TYPE_CHECKING`` is still an architectural dependency: a module that needs
the concrete type of an outer implementation knows about that implementation
even though the import is erased at runtime. Such edges are evaluated against
the same matrix; the guard is recorded only so the diagnostic can say so.
External and standard-library imports are ignored in every position.

There are **no allowlisted exceptions**. The two edge classes that would have
needed one were removed structurally in P1 instead: the canonical value
contracts moved to the L0 kernel (:mod:`congine_core.models`), and the
background sync worker was retyped against the L1
:class:`~congine_core.ports.sync_runner.ISyncRunner` port.

The public package ``congine_core/__init__.py`` is the one excluded *source*,
because aggregating the supported public surface is its explicit
responsibility. It is never an allowed *target* for internal modules — importing
through it would hide a real edge behind an apparently-L0 one. Literal
``__import__`` and ``importlib.import_module`` calls are checked as imports too.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_PACKAGE: Final = "congine_core"
_PUBLIC_AGGREGATOR_LAYER: Final = 6
_LAYER_BY_DIRECTORY: Final = {
    "ports": 1,
    "domain": 2,
    "usecases": 3,
    "infrastructure": 4,
    "adapters": 5,
}
_LAYER_NAMES: Final = {
    0: "L0 kernel",
    1: "L1 ports",
    2: "L2 domain",
    3: "L3 use cases",
    4: "L4 infrastructure",
    5: "L5 adapters",
    _PUBLIC_AGGREGATOR_LAYER: "public package aggregator",
}

#: What each layer may depend on, stated explicitly rather than derived from the
#: layer numbers. Read a row as "a module in this layer may import these layers".
#:
#: The two entries that a numeric ``target <= source`` rule gets wrong are the
#: absences in L4: infrastructure may use the kernel (L0) and the ports it
#: implements (L1), but must not reach into domain (L2) or use cases (L3).
#: Dependency inversion is the whole point of the ports layer, and an
#: infrastructure module that imports a use case has bypassed it.
#:
#: ``_PUBLIC_AGGREGATOR_LAYER`` deliberately appears in no row, so an internal
#: module importing ``from congine_core import ...`` is rejected from every
#: layer, including L5.
_ALLOWED_DEPENDENCIES: Final[dict[int, frozenset[int]]] = {
    0: frozenset({0}),
    1: frozenset({0, 1}),
    2: frozenset({0, 1, 2}),
    3: frozenset({0, 1, 2, 3}),
    4: frozenset({0, 1, 4}),
    5: frozenset({0, 1, 2, 3, 4, 5}),
}


@dataclass(frozen=True)
class LayerViolation:
    """One import the layer dependency matrix does not permit."""

    path: Path
    line: int
    source_layer: int
    target_layer: int
    target_module: str
    #: True when the import sits under ``if TYPE_CHECKING``. Diagnostic only —
    #: it never affects whether the edge is a violation.
    type_checking: bool = False

    def render(self, source_root: Path) -> str:
        relative_path = self.path.relative_to(source_root.parent)
        context = " under TYPE_CHECKING" if self.type_checking else ""
        return (
            f"{relative_path}:{self.line}: {_LAYER_NAMES[self.source_layer]} "
            f"must not import {_LAYER_NAMES[self.target_layer]} "
            f"({self.target_module}){context}"
        )


def _source_layer(path: Path, source_root: Path) -> int:
    relative = path.relative_to(source_root)
    if len(relative.parts) == 1:
        return 0
    directory = relative.parts[0]
    try:
        return _LAYER_BY_DIRECTORY[directory]
    except KeyError as exc:
        raise ValueError(
            f"Unclassified source directory {directory!r} for {relative}"
        ) from exc


def _module_name(path: Path, source_root: Path) -> tuple[str, bool]:
    relative = path.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join([_PACKAGE, *parts]), is_package


def _target_layer(module: str) -> int | None:
    parts = module.split(".")
    if not parts or parts[0] != _PACKAGE:
        return None
    if len(parts) == 1:
        # The root __init__.py may aggregate outward as a source file, but
        # production internals must not import through that aggregate surface:
        # doing so would hide the real dependency behind an apparently-L0 edge.
        return _PUBLIC_AGGREGATOR_LAYER
    return _LAYER_BY_DIRECTORY.get(parts[1], 0)


@dataclass(frozen=True)
class _ScopeAliases:
    bound: frozenset[str]
    direct_type_checking: frozenset[str]
    typing_modules: frozenset[str]
    import_module_functions: frozenset[str]
    importlib_modules: frozenset[str]


@dataclass(frozen=True)
class _ScopeFrame:
    kind: str
    aliases: _ScopeAliases


@dataclass(frozen=True)
class _RecordedImport:
    """One import edge discovered in a source file, before classification."""

    module: str
    line: int
    type_checking: bool


def _scope_aliases(
    statements: list[ast.stmt], parameters: set[str] | None = None
) -> _ScopeAliases:
    """Resolve trusted aliases and shadows for exactly one lexical scope."""

    class BindingVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.bound = set(parameters or ())
            self.rebound = set(parameters or ())
            self.direct_type_checking: set[str] = set()
            self.typing_modules: set[str] = set()
            self.import_module_functions: set[str] = set()
            self.importlib_modules: set[str] = set()

        def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
            if isinstance(node.ctx, ast.Store):
                self.bound.add(node.id)
                self.rebound.add(node.id)

        def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
            for alias in node.names:
                name = alias.asname or alias.name.split(".", maxsplit=1)[0]
                self.bound.add(name)
                if alias.name in {"typing", "typing_extensions"}:
                    self.typing_modules.add(name)
                elif alias.name == "importlib":
                    self.importlib_modules.add(name)
                else:
                    self.rebound.add(name)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
            for alias in node.names:
                name = alias.asname or alias.name
                self.bound.add(name)
                if (
                    node.module in {"typing", "typing_extensions"}
                    and alias.name == "TYPE_CHECKING"
                ):
                    self.direct_type_checking.add(name)
                elif node.module == "importlib" and alias.name == "import_module":
                    self.import_module_functions.add(name)
                else:
                    self.rebound.add(name)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            self.bound.add(node.name)
            self.rebound.add(node.name)

        def visit_AsyncFunctionDef(  # noqa: N802
            self, node: ast.AsyncFunctionDef
        ) -> None:
            self.bound.add(node.name)
            self.rebound.add(node.name)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            self.bound.add(node.name)
            self.rebound.add(node.name)

        def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
            return

    visitor = BindingVisitor()
    for statement in statements:
        visitor.visit(statement)

    # Any non-alias binding with the same spelling makes the alias ambiguous;
    # inspect the branch as runtime code rather than risk hiding an edge.
    alias_categories = [
        visitor.direct_type_checking,
        visitor.typing_modules,
        visitor.import_module_functions,
        visitor.importlib_modules,
    ]
    ambiguous = set().union(
        *(
            left & right
            for index, left in enumerate(alias_categories)
            for right in alias_categories[index + 1 :]
        )
    )
    blocked = visitor.rebound | ambiguous
    return _ScopeAliases(
        bound=frozenset(visitor.bound),
        direct_type_checking=frozenset(visitor.direct_type_checking - blocked),
        typing_modules=frozenset(visitor.typing_modules - blocked),
        # Dynamic imports are enforcement edges, never exemptions. Preserve a
        # discovered loader alias even when another binding makes it ambiguous;
        # a conservative false positive is safer than a layer-check bypass.
        import_module_functions=frozenset(visitor.import_module_functions),
        importlib_modules=frozenset(visitor.importlib_modules),
    )


def _parameter_names(arguments: ast.arguments) -> set[str]:
    return {
        argument.arg
        for argument in [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *([arguments.vararg] if arguments.vararg is not None else []),
            *([arguments.kwarg] if arguments.kwarg is not None else []),
        ]
    }


class _RuntimeImportVisitor(ast.NodeVisitor):
    def __init__(self, module_name: str, is_package: bool, tree: ast.Module) -> None:
        self._module_name = module_name
        self._is_package = is_package
        self._scopes = [_ScopeFrame("module", _scope_aliases(tree.body))]
        #: Depth of enclosing ``if TYPE_CHECKING`` bodies. Recorded on each
        #: import for diagnostics; enforcement is identical at any depth.
        self._type_checking_depth = 0
        self.imports: list[_RecordedImport] = []

    def _record(self, module: str, line: int) -> None:
        self.imports.append(
            _RecordedImport(module, line, self._type_checking_depth > 0)
        )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self._record(alias.name, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = self._resolve_from_module(node)
        if not module:
            return
        if module == _PACKAGE or node.module is None:
            for alias in node.names:
                candidate = f"{module}.{alias.name}"
                if alias.name in _LAYER_BY_DIRECTORY or node.module is None:
                    self._record(candidate, node.lineno)
                    continue
                self._record(module, node.lineno)
            return
        self._record(module, node.lineno)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        """Visit both arms; a ``TYPE_CHECKING`` body is enforced, not skipped.

        The guard is still resolved, for two reasons. The ``else`` arm of an
        ``if TYPE_CHECKING`` is ordinary runtime code and must not be tagged as
        static-only, and tagging the body lets the diagnostic name the guard.
        """
        guard = self._type_checking_guard(node.test)
        static_body = guard is True
        static_orelse = guard is False

        # The test expression itself is runtime code and may hide a literal
        # dynamic import, so it is still visited.
        self.visit(node.test)
        self._visit_branch(node.body, static=static_body)
        self._visit_branch(node.orelse, static=static_orelse)

    def _visit_branch(self, statements: list[ast.stmt], *, static: bool) -> None:
        if static:
            self._type_checking_depth += 1
        try:
            for child in statements:
                self.visit(child)
        finally:
            if static:
                self._type_checking_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(  # noqa: N802
        self, node: ast.AsyncFunctionDef
    ) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        for expression in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(expression)
        self._scopes.append(_ScopeFrame("class", _scope_aliases(node.body)))
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self._scopes.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Record common dynamic imports when their module name is literal."""
        is_dynamic_import = (
            isinstance(node.func, ast.Name)
            and (
                (node.func.id == "__import__" and not self._is_bound(node.func.id))
                or self._resolves_as(node.func.id, "import_module_functions")
            )
        ) or (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and self._resolves_as(node.func.value.id, "importlib_modules")
        )
        if (
            is_dynamic_import
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            self._record(node.args[0].value, node.lineno)
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for expression in [
            *node.decorator_list,
            *node.args.defaults,
            *[default for default in node.args.kw_defaults if default is not None],
        ]:
            self.visit(expression)
        self._scopes.append(
            _ScopeFrame(
                "function", _scope_aliases(node.body, _parameter_names(node.args))
            )
        )
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self._scopes.pop()

    def _resolves_as(self, name: str, category: str) -> bool:
        for frame in self._visible_scope_frames():
            scope = frame.aliases
            aliases = getattr(scope, category)
            if name in aliases:
                return True
            if name in scope.bound:
                return False
        return False

    def _is_bound(self, name: str) -> bool:
        return any(
            name in frame.aliases.bound for frame in self._visible_scope_frames()
        )

    def _visible_scope_frames(self) -> list[_ScopeFrame]:
        """Return frames Python can actually resolve from the current scope."""
        current_index = len(self._scopes) - 1
        current_kind = self._scopes[current_index].kind
        visible: list[_ScopeFrame] = []
        for index in range(current_index, -1, -1):
            frame = self._scopes[index]
            if frame.kind == "class" and (
                current_kind == "function"
                or (current_kind == "class" and index != current_index)
            ):
                continue
            visible.append(frame)
        return visible

    def _resolve_from_module(self, node: ast.ImportFrom) -> str:
        if node.level == 0:
            return node.module or ""

        package_parts = self._module_name.split(".")
        if not self._is_package:
            package_parts.pop()
        ascend = node.level - 1
        if ascend > len(package_parts):
            return ""
        if ascend:
            package_parts = package_parts[:-ascend]
        if node.module:
            package_parts.extend(node.module.split("."))
        return ".".join(package_parts)

    def _type_checking_guard(self, test: ast.expr) -> bool | None:
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            if self._is_type_checking_reference(test.operand):
                return False
            return None
        if self._is_type_checking_reference(test):
            return True
        return None

    def _is_type_checking_reference(self, expression: ast.expr) -> bool:
        if isinstance(expression, ast.Name):
            return self._resolves_as(expression.id, "direct_type_checking")
        return (
            isinstance(expression, ast.Attribute)
            and expression.attr == "TYPE_CHECKING"
            and isinstance(expression.value, ast.Name)
            and self._resolves_as(expression.value.id, "typing_modules")
        )


def check_architecture(source_root: Path) -> list[LayerViolation]:
    """Return every import beneath ``source_root`` the layer matrix forbids."""
    source_root = source_root.resolve()
    public_aggregator = source_root / "__init__.py"
    violations: list[LayerViolation] = []

    for path in sorted(source_root.rglob("*.py")):
        if path == public_aggregator:
            continue
        source_layer = _source_layer(path, source_root)
        module_name, is_package = _module_name(path, source_root)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _RuntimeImportVisitor(module_name, is_package, tree)
        visitor.visit(tree)

        allowed = _ALLOWED_DEPENDENCIES[source_layer]
        for recorded in visitor.imports:
            target_layer = _target_layer(recorded.module)
            # ``None`` means stdlib or third-party: outside the matrix entirely.
            if target_layer is None or target_layer in allowed:
                continue
            violations.append(
                LayerViolation(
                    path=path,
                    line=recorded.line,
                    source_layer=source_layer,
                    target_layer=target_layer,
                    target_module=recorded.module,
                    type_checking=recorded.type_checking,
                )
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src" / _PACKAGE,
        help="path to the congine_core package",
    )
    args = parser.parse_args(argv)
    source_root = args.source_root.resolve()
    violations = check_architecture(source_root)
    if violations:
        print("Forbidden layer dependencies:")
        for violation in violations:
            print(f"  {violation.render(source_root)}")
        return 1

    file_count = sum(1 for _ in source_root.rglob("*.py"))
    print(f"Architecture check passed: {file_count} source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
