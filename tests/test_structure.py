# SPDX-License-Identifier: GPL-3.0-or-later
"""The structure check catches each problem it names, and this repository has none."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture(scope="module")
def structure():
    spec = importlib.util.spec_from_file_location("structure", ROOT / "scripts/structure.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["structure"] = module
    spec.loader.exec_module(module)
    return module


def package(tmp_path: pathlib.Path, modules: dict[str, str]) -> pathlib.Path:
    folder = tmp_path / "src/pkg"
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("")
    for name, text in modules.items():
        (folder / f"{name}.py").write_text(text)
    return folder


def test_this_repository_keeps_its_structure(structure):
    found = structure.measure(ROOT)
    assert found["problems"] == []
    assert found["cycles"] == 0


def test_a_module_past_its_folders_limit_is_too_big(structure, tmp_path):
    package(tmp_path, {"big": "x = 1\n" * 11, "small": "x = 1\n"})
    found = structure.oversized(tmp_path, {"src": 10})
    assert len(found) == 1
    assert "big.py is 11 lines" in found[0]


def test_a_core_module_that_imports_an_adapter_breaks_the_layers(structure, tmp_path):
    pkg = package(tmp_path, {"core": "from pkg import adapter\n", "adapter": "from pkg.core import x\n"})
    found = structure.layer_breaches(pkg, {"core": 1, "adapter": 2})
    assert found == ["core (layer 1) imports adapter (layer 2)"]


def test_a_module_with_no_layer_breaks_the_layers(structure, tmp_path):
    pkg = package(tmp_path, {"new": "x = 1\n"})
    assert structure.layer_breaches(pkg, {}) == ["new has no layer: give it one in [tool.quality.layers]"]


def test_modules_that_import_each_other_are_a_cycle_and_a_lazy_import_is_not(structure, tmp_path):
    pkg = package(tmp_path, {"a": "from pkg import b\n", "b": "import pkg.a\n"})
    assert structure.cycles(pkg) == 1
    (pkg / "b.py").write_text("def later():\n    from pkg import a\n")
    assert structure.cycles(pkg) == 0


def test_copied_code_is_the_share_of_lines_in_blocks_that_appear_twice(structure, tmp_path):
    block = "".join(f"line_{n} = {n}\n" for n in range(6))
    package(tmp_path, {"a": block + "only_here = 1\n", "b": "    " + block.replace("\n", "\n    ")})
    assert structure.duplication(tmp_path, ["src"], 6) == round(100 * 12 / 13, 2)


def test_complexity_is_the_most_tangled_function_and_a_nested_one_counts_alone(structure, tmp_path):
    pkg = package(
        tmp_path,
        {
            "m": "def f(x):\n    if x:\n        return 1\n    def g(y):\n        if y and x:\n"
            "            return 2\n    return 0\n"
        },
    )
    assert structure.complexity(pkg) == {"m.py": 3}
