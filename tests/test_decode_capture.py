# SPDX-License-Identifier: GPL-3.0-or-later
"""The capture decoder reads a synthetic scope CSV back to the bytes that made it."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
BIT = 250e-6
STEP = 1.6e-6


@pytest.fixture(scope="module")
def decode():
    spec = importlib.util.spec_from_file_location("decode_capture", ROOT / "scripts/decode_capture.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["decode_capture"] = module
    spec.loader.exec_module(module)
    return module


def capture(tmp_path: pathlib.Path, payload: bytes) -> pathlib.Path:
    """A Tek-style CSV: idle 12 V, a 2.6 ms break, half a bit high, then 8N1 frames."""
    levels = [(1, 2e-3), (0, 2.6e-3), (1, BIT / 2)]
    for byte in payload:
        levels += [(0, BIT), *[((byte >> k) & 1, BIT) for k in range(8)], (1, BIT)]
    levels.append((1, 3 * BIT))
    lines = ["Model,MSO2024", "TIME,CH1,CH1 Peak Detect"]
    t = 0.0
    for level, length in levels:
        end = t + length
        while t < end:
            lines.append(f"{t:.6e},{12.0 if level else 0.0},0")
            t += STEP
    path = tmp_path / "capture.csv"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_a_capture_decodes_to_the_bytes_that_made_it(decode, tmp_path):
    found = decode.runs(decode.samples(capture(tmp_path, bytes([0x55, 0x01, 0x00, 0x86]))), 6.0)
    bit = decode.fit_bit(found)
    assert bit == pytest.approx(BIT, rel=0.02)
    assert decode.frames(decode.bits(found, bit)) == ["00!F", "55", "01", "00", "86"]


def test_the_short_high_after_a_break_does_not_halve_the_bit_time(decode, tmp_path):
    found = decode.runs(decode.samples(capture(tmp_path, bytes([0x55, 0x55]))), 6.0)
    assert decode.fit_bit(found) == pytest.approx(BIT, rel=0.02)
