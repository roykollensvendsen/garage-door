#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the shape of the code: module size, layers, import cycles, copied code.

The settings are in pyproject.toml under [tool.quality], so the same file
works in another repository with its own settings:

- `max_lines`: the most lines a module may have, per folder. A module past
  it does too much; split it.
- `layers`: each module of the package and its layer. A module may import,
  when it loads, only modules in lower layers. A module with no layer fails,
  so a new module has to be given one.
- `duplication`: the folders searched for copied blocks of `block` lines
  (ignoring indentation). The share of lines in such blocks is measured
  here and held by the quality ratchet (scripts/ratchet.py).

    python3 scripts/structure.py            # exit 1 on an oversized module, a layer breach or a cycle
    python3 scripts/structure.py --json     # the measures, for the ratchet

The complexity, cycle, layer and duplication measures follow claude-voice's
scripts/ratchet.py (same author, same licence). Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
CODE = (".py", ".h", ".hpp", ".c", ".cpp")
DECISIONS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.IfExp,
    ast.Assert,
    ast.match_case,
)
NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def settings(root: Path = ROOT) -> dict[str, Any]:
    """The [tool.quality] table of pyproject.toml."""
    return dict(tomllib.loads((root / "pyproject.toml").read_text())["tool"]["quality"])


def _files(root: Path, folder: str) -> list[Path]:
    return sorted(p for p in (root / folder).rglob("*") if p.suffix in CODE and "build" not in p.parts)


# -- module size -------------------------------------------------------------


def oversized(root: Path, max_lines: dict[str, int]) -> list[str]:
    """Every module longer than its folder allows."""
    return [
        f"{path.relative_to(root)} is {n} lines; {folder}/ allows {limit}: split it"
        for folder, limit in max_lines.items()
        for path in _files(root, folder)
        if (n := len(path.read_text().splitlines())) > limit
    ]


def largest(root: Path, max_lines: dict[str, int]) -> int:
    """The length of the longest module in any checked folder."""
    return max((len(p.read_text().splitlines()) for f in max_lines for p in _files(root, f)), default=0)


# -- complexity --------------------------------------------------------------


def _function_complexity(fn: ast.AST) -> int:
    """McCabe's count for one function, leaving out the functions defined inside it."""
    count = 1
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        if isinstance(node, NESTED):
            continue
        if isinstance(node, DECISIONS):
            count += 1
        elif isinstance(node, ast.BoolOp):
            count += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            count += 1 + len(node.ifs)
        stack.extend(ast.iter_child_nodes(node))
    return count


def complexity(package: Path) -> dict[str, int]:
    """The most tangled function in each module of `package`, by McCabe's count."""
    out = {}
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text())
        functions = (n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        scores = [_function_complexity(n) for n in functions]
        if scores:
            out[path.relative_to(package).as_posix()] = max(scores)
    return out


# -- imports: cycles and layers ----------------------------------------------


def _modules(package: Path) -> set[str]:
    return {p.stem for p in package.glob("*.py") if p.stem != "__init__"}


def imports(path: Path, package: str, names: set[str]) -> set[str]:
    """The package's modules `path` imports when it loads (not inside a function)."""
    found = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                found.update(a.name for a in node.names if not base and a.name in names)
                if base:
                    found.add(base.split(".")[0])
            elif base.startswith(package + "."):
                found.add(base.split(".")[1])
            elif base == package:
                found.update(a.name for a in node.names if a.name in names)
        elif isinstance(node, ast.Import):
            found.update(a.name.split(".")[1] for a in node.names if a.name.startswith(package + "."))
    return found & names


def cycles(package: Path) -> int:
    """How many groups of modules import each other in a circle when they load."""
    names = _modules(package)
    graph = {n: imports(package / f"{n}.py", package.name, names) - {n} for n in names}
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    groups = 0

    def visit(node: str) -> None:  # Tarjan's strongly connected components
        nonlocal groups
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        for nxt in graph[node]:
            if nxt not in index:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            size = 0
            while True:
                top = stack.pop()
                on_stack.discard(top)
                size += 1
                if top == node:
                    break
            groups += size > 1

    for name in sorted(names):
        if name not in index:
            visit(name)
    return groups


def layer_breaches(package: Path, layers: dict[str, int]) -> list[str]:
    """Every load-time import that reaches up or sideways, and every module with no layer."""
    names = _modules(package)
    found = []
    for name in sorted(names):
        if name not in layers:
            found.append(f"{name} has no layer: give it one in [tool.quality.layers]")
            continue
        found.extend(
            f"{name} (layer {layers[name]}) imports {used} (layer {layers[used]})"
            for used in sorted(imports(package / f"{name}.py", package.name, names) - {name})
            if used in layers and layers[used] >= layers[name]
        )
    return found


# -- copied code -------------------------------------------------------------


def duplication(root: Path, folders: list[str], block: int) -> float:
    """The share of non-blank lines, in percent, in a block of `block` lines that appears twice."""
    files = {
        p: [" ".join(line.split()) for line in p.read_text().splitlines() if line.strip()]
        for folder in folders
        for p in _files(root, folder)
    }
    where: dict[tuple[str, ...], list[tuple[Path, int]]] = {}
    for path, lines in files.items():
        for i in range(len(lines) - block + 1):
            where.setdefault(tuple(lines[i : i + block]), []).append((path, i))
    copied = {
        (p, j) for spots in where.values() if len(spots) > 1 for p, i in spots for j in range(i, i + block)
    }
    total = sum(len(lines) for lines in files.values())
    return round(100 * len(copied) / total, 2) if total else 0.0


# -- the command -------------------------------------------------------------


def measure(root: Path = ROOT) -> dict[str, Any]:
    """Every structural measure, and the problems that fail on their own."""
    cfg = settings(root)
    package = root / cfg["package"]
    breaches = layer_breaches(package, cfg["layers"])
    sizes = oversized(root, cfg["max_lines"])
    return {
        "complexity": complexity(package),
        "cycles": cycles(package),
        "layer_violations": len(breaches),
        "duplication": duplication(root, cfg["duplication"], cfg.get("block", 6)),
        "largest_module": largest(root, cfg["max_lines"]),
        "oversized_modules": len(sizes),
        "problems": sizes + breaches,
    }


def main() -> int:
    """Print the problems, or with --json every measure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the measures as JSON")
    args = parser.parse_args()
    found = measure()
    if args.json:
        sys.stdout.write(json.dumps(found, indent=2, sort_keys=True) + "\n")
        return 0
    problems = found["problems"] + (["modules import each other in a circle"] if found["cycles"] else [])
    for problem in problems:
        sys.stderr.write(problem + "\n")
    if not problems:
        sys.stdout.write(
            f"structure holds: largest module {found['largest_module']} lines, no layer breach, "
            f"no cycle, {found['duplication']} % copied\n"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
