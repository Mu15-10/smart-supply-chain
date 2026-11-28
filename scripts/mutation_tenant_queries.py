"""AST-discovered tenant-predicate mutation audit and manifest guard."""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

MANIFEST_PATH = Path(__file__).with_name("tenant_predicate_manifest.json")


@dataclass(frozen=True)
class Target:
    id: str
    path: str
    function: str
    ordinal: int
    line: int
    column: int
    end_line: int
    end_column: int
    expression: str


# Only the two genuinely equivalent mutants remain classified after the corruption tests.
SURVIVOR_CLASSES: dict[str, str] = {
    "backend/app/main.py::refresh::1": (
        "equivalent: User.id is globally unique and the refresh row supplies the same tenant_id"
    ),
    "backend/app/main.py::claim_idem::2": (
        "equivalent: uq_idem_tenant_route_key makes a conflicting row tenant-identical"
    ),
}


def _contains_tenant_compare(node: ast.AST) -> bool:
    return isinstance(node, ast.Compare) and any(
        isinstance(candidate, ast.Attribute) and candidate.attr == "tenant_id"
        for candidate in ast.walk(node)
    )


def discover_file(path: Path, relative: str) -> list[Target]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    function_for: dict[ast.AST, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                function_for[child] = node.name
    ordinal_by_function: dict[str, int] = {}
    targets: list[Target] = []
    for node in ast.walk(tree):
        if not _contains_tenant_compare(node) or not hasattr(node, "end_lineno"):
            continue
        assert isinstance(node, ast.Compare)
        function = function_for.get(node, "<module>")
        ordinal_by_function[function] = ordinal_by_function.get(function, 0) + 1
        ordinal = ordinal_by_function[function]
        expression = ast.get_source_segment(source, node)
        if not expression:
            continue
        target_id = f"{relative}::{function}::{ordinal}"
        targets.append(
            Target(
                id=target_id,
                path=relative,
                function=function,
                ordinal=ordinal,
                line=node.lineno,
                column=node.col_offset,
                end_line=node.end_lineno,
                end_column=node.end_col_offset,
                expression=expression,
            )
        )
    return sorted(targets, key=lambda target: (target.path, target.line, target.column))


def discover(app_root: Path) -> list[Target]:
    targets: list[Target] = []
    for path in sorted(app_root.rglob("*.py")):
        targets.extend(
            discover_file(path, path.relative_to(app_root.parent.parent).as_posix())
        )
    return targets


def manifest_records(targets: list[Target]) -> list[dict[str, object]]:
    return [
        {
            "id": target.id,
            "path": target.path,
            "function": target.function,
            "ordinal": target.ordinal,
            "expression": target.expression,
        }
        for target in targets
    ]


def manifest_guard(
    targets: list[Target], manifest_path: Path = MANIFEST_PATH
) -> list[str]:
    expected = {record["id"]: record for record in manifest_records(targets)}
    actual = {
        record["id"]: record
        for record in json.loads(manifest_path.read_text(encoding="utf-8"))
    }
    errors: list[str] = []
    for target_id in sorted(set(expected) | set(actual)):
        if target_id not in expected:
            errors.append(f"manifest has stale target: {target_id}")
        elif target_id not in actual:
            errors.append(
                f"new tenant predicate requires manifest/classification: {target_id}"
            )
        elif expected[target_id] != actual[target_id]:
            errors.append(f"manifest record changed: {target_id}")
    classifications = set(SURVIVOR_CLASSES)
    unknown = classifications - set(expected)
    errors.extend(
        f"classification has no discovered target: {target_id}"
        for target_id in sorted(unknown)
    )
    return errors


def _offsets(source: str) -> list[int]:
    offsets = [0]
    for index, char in enumerate(source):
        if char == "\n":
            offsets.append(index + 1)
    return offsets


def mutate(source: str, target: Target) -> str:
    offsets = _offsets(source)
    start = offsets[target.line - 1] + target.column
    end = offsets[target.end_line - 1] + target.end_column
    return source[:start] + "True" + source[end:]


def run_mutant(repo_root: Path, target: Target, pytest_path: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="tenant-mutant-") as temporary:
        copy_root = Path(temporary) / repo_root.name
        shutil.copytree(
            repo_root,
            copy_root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
        )
        source_path = copy_root / target.path
        source = source_path.read_text(encoding="utf-8")
        source_path.write_text(mutate(source, target), encoding="utf-8")
        completed = subprocess.run(
            ["pytest", "-q", pytest_path],
            cwd=copy_root / "backend",
            capture_output=True,
            text=True,
            check=False,
        )
        return (
            "FAIL_DETECTED" if completed.returncode else "SURVIVOR",
            completed.stdout[-1200:],
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pytest", default="tests/test_phase1c_isolation.py")
    parser.add_argument("--json", dest="json_path", type=Path)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--guard-only", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    targets = discover(repo_root / "backend" / "app")
    if args.write_manifest:
        MANIFEST_PATH.write_text(
            json.dumps(manifest_records(targets), indent=2) + "\n", encoding="utf-8"
        )
        return 0
    errors = manifest_guard(targets)
    if errors:
        print("CI GUARD FAILURE: " + " | ".join(errors))
        return 1
    if args.guard_only:
        print(f"manifest guard passed: {len(targets)} tenant predicates")
        return 0

    results: list[dict[str, object]] = []
    for target in targets:
        result, output = run_mutant(repo_root, target, args.pytest)
        classification = SURVIVOR_CLASSES.get(target.id)
        if result == "SURVIVOR" and classification is None:
            classification = "UNCLASSIFIED_SURVIVOR"
        results.append(
            {
                "target": asdict(target),
                "result": result,
                "classification": classification,
                "tail": output,
            }
        )
        print(
            f"{target.id} | {result}"
            + (f" | {classification}" if classification else "")
        )
    if any(item["classification"] == "UNCLASSIFIED_SURVIVOR" for item in results):
        print("CI GUARD FAILURE: survivor classification is required")
        return 1
    if args.json_path:
        args.json_path.write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(
        f"discovered={len(targets)} tested={sum(item['result'] == 'FAIL_DETECTED' for item in results)} classified={sum(bool(item['classification']) for item in results)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
