#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decode a one-wire serial capture saved by a Tektronix scope as CSV.

Reads the TIME and CH1 columns of a "Spreadsheet file" waveform, turns the
voltage into high and low runs (a threshold with hysteresis), finds the bit
time from the run lengths, and decodes UART frames: idle high, start bit low,
8 data bits LSB first, no parity, one stop bit. A long low before the first
frame is a break; it reads as 0x00 with a framing error and is reported as
such. Read-only: it never writes anywhere.

    python3 scripts/decode_capture.py docs/captures/<file>.csv [--threshold 6] [--bit-us 250.8]

Without --bit-us the bit time is fitted. The first high after a break can be
any length (half a bit on the LM80EVF), so it is left out of the fit.
Security+ 2.0 packets start with the sync bytes 55 01 00 (ratgdo's receiver);
they are marked when found.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HYSTERESIS = 1.0  # volts either side of the threshold
SYNC = [0x55, 0x01, 0x00]


def samples(path: Path) -> list[tuple[float, float]]:
    """(time in s, CH1 in V) for every data row; the header rows are skipped."""
    out = []
    with path.open(newline="") as f:
        for row in csv.reader(f):
            try:
                out.append((float(row[0]), float(row[1])))
            except (ValueError, IndexError):
                continue
    return out


def runs(points: list[tuple[float, float]], threshold: float) -> list[tuple[int, float]]:
    """(level, seconds) for each stretch above or below the threshold."""
    level = int(points[0][1] > threshold)
    start = points[0][0]
    found = []
    for t, v in points[1:]:
        if (level and v < threshold - HYSTERESIS) or (not level and v > threshold + HYSTERESIS):
            found.append((level, t - start))
            level, start = 1 - level, t
    found.append((level, points[-1][0] - start))
    return found


def fit_bit(found: list[tuple[int, float]]) -> float:
    """The bit time, in seconds: the shortest inner run, refined over all of them.

    Any whole fraction of the bit would fit the runs as well, so the fit
    starts from the shortest run, which is one bit whenever one single bit
    stands alone (the 0x55 sync byte has nothing else).
    """
    inner = [d for _, d in found[3:-1]]  # not the idle, the break, the first high or the cut-off end
    first = min(inner)
    return sum(inner) / sum(round(d / first) for d in inner)


def bits(found: list[tuple[int, float]], bit: float) -> list[int]:
    """The line as one level per bit time, from the first run after the idle."""
    out: list[int] = []
    for level, d in found[1:]:
        out += [level] * max(1, round(d / bit))
    return out


def frames(line: list[int]) -> list[str]:
    """8N1 frames as hex; '!F' marks a missing stop bit, 'cut' a frame the capture ends in."""
    out = []
    i = 0
    while i < len(line):
        if line[i]:
            i += 1
            continue
        if i + 10 > len(line):
            out.append("cut")
            break
        value = sum(b << k for k, b in enumerate(line[i + 1 : i + 9]))
        out.append(f"{value:02X}" + ("" if line[i + 9] else "!F"))
        i += 10
    return out


def main() -> int:
    """Print the runs, the bit time and the bytes."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path)
    parser.add_argument("--threshold", type=float, default=6.0, help="volts between low and high")
    parser.add_argument("--bit-us", type=float, help="bit time in microseconds; fitted if left out")
    args = parser.parse_args()
    found = runs(samples(args.csv), args.threshold)
    bit = args.bit_us * 1e-6 if args.bit_us else fit_bit(found)
    sys.stdout.write(
        "runs (level, us): " + " ".join(f"{'HL'[1 - lv]}{d * 1e6:.1f}" for lv, d in found) + "\n"
    )
    sys.stdout.write(f"bit time {bit * 1e6:.1f} us, {1 / bit:.0f} baud\n")
    decoded = frames(bits(found, bit))
    sys.stdout.write("8N1: " + " ".join(decoded) + "\n")
    values = [int(x[:2], 16) for x in decoded if x != "cut" and not x.endswith("!F")]
    at = next((i for i in range(len(values)) if values[i : i + 3] == SYNC), None)
    if at is not None:
        sys.stdout.write(
            f"Security+ 2.0 sync 55 01 00 found; {len(values) - at} bytes from it in this capture\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
