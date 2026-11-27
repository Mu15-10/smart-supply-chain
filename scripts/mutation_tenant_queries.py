"""AST-discovered tenant-predicate mutation audit.

The audit discovers every comparison containing ``.tenant_id`` under ``backend/app``.
Each comparison is replaced with the SQL-safe literal ``True`` in a disposable copy,
then the isolation suite is executed.  The source tree is never modified: every mutant
lives in its own TemporaryDirectory.  A failed test or import/syntax failure means the
mutant was detected.  Survivors must be explicitly classified in ``SURVIVOR_CLASSES``.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    id: str
    path: str
    line: int
    column: int
    end_line: int
    end_column: int
    expression: str


# A survivor is not silently accepted.  Each entry has a precise reason and is reviewed
# against the database invariant or the documented test gap.
SURVIVOR_CLASSES: dict[str, str] = {
    "backend/app/main.py:b9b6e1332b06": (
        "equivalent: User.id is globally unique and the refresh row supplies the same tenant_id"
    ),
    "backend/app/main.py:91acde7e9e3d": (
        "test-gap: add a corrupted inventory row referencing another tenant's product and assert no reorder-point leakage"
    ),
    "backend/app/main.py:a584ab3ee3d0": (
        "test-gap: add corrupted cross-tenant inventory rows and assert adjust/approve/receive cannot update them"
    ),
    "backend/app/main.py:71db307f96fa": (
        "equivalent: uq_idem_tenant_route_key makes a conflicting row tenant-identical"
    ),
}


def _target_id(path: str, node: ast.Compare, expression: str) -> str:
    digest = hashlib.sha256(expression.encode("utf-8")).hexdigest()[:12]
    # Digest-only identity remains stable when comments or formatting shift line numbers.
    return f"{path}:{digest}"


def discover(app_root: Path) -> list[Target]:
    targets: list[Target] = []
    for path in sorted(app_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        relative = path.relative_to(app_root.parent.parent).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or not hasattr(node, "end_lineno"):
                continue
            segment = ast.get_source_segment(source, node)
            if not segment or not any(
                isinstance(candidate, ast.Attribute) and candidate.attr == "tenant_id"
                for candidate in ast.walk(node)
            ):
                continue
            targets.append(
                Target(
                    id=_target_id(relative, node, segment),
                    path=relative,
                    line=node.lineno,
                    column=node.col_offset,
                    end_line=node.end_lineno,
                    end_column=node.end_col_offset,
                    expression=segment,
                )
            )
    return targets


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
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    targets = discover(repo_root / "backend" / "app")
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

    discovered = {target.id for target in targets}
    tested = {
        item["target"]["id"] for item in results if item["result"] == "FAIL_DETECTED"
    }
    classified = {item["target"]["id"] for item in results if item["classification"]}
    if discovered != tested | classified:
        missing = sorted(discovered - tested - classified)
        print(f"CI GUARD FAILURE: undispositioned targets: {json.dumps(missing)}")
        return 1
    if any(item["classification"] == "UNCLASSIFIED_SURVIVOR" for item in results):
        print("CI GUARD FAILURE: survivor classification is required")
        return 1

    print(
        f"discovered={len(discovered)} tested={len(tested)} classified={len(classified)}"
    )
    if args.json_path:
        args.json_path.write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
