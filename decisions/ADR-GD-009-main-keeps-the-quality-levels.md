<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# ADR-GD-009: Main keeps the quality levels, so a pull request never records them

## Status

Accepted 2026-11-10, as rule 16 of the shared voice-plugin standard
(claude-voice `docs/plugin-standard.md`). Roy agreed to the standard through
the claude-voice session, which relayed it here. The same decision as
claude-voice's ADR-CV-009, which proved itself in that repository's CI first.

## Context

The quality ratchet stops the code getting worse: coverage of the laptop code
and of the controller logic, mutation, the number of tests, lint and type
errors, layers, cycles, module size, copied code and complexity. Until now
the levels lived in `quality.json`, and every change had to record the exact
levels it reached, or the check failed.

On 2026-11-10 that made the file a queue. Four pull requests were open at
once, and each one that added a test changed the recorded test count, so
whichever merged first broke the others. The same day showed the other
weakness: the levels in the file had not changed since 2026-11-04, while the
code had slipped, because nothing ran the ratchet.

## Options considered

- **Keep the file as it was.** Every merge breaks every other open pull
  request. Not taken.
- **Measure main and the pull request in every check.** Nothing stored, but
  each check takes twice as long. Not taken, except as the fallback below.
- **Main keeps its measured levels with each of its runs; a pull request
  compares with them.** **Chosen.**

## Decision

- **After every push to main**, CI measures the levels and keeps them with
  that run, as the artifact `quality-levels`.
- **A pull request's check** takes the levels main kept for the commit it is
  based on, and fails only when a level is worse, unless a
  `Ratchet-Exception: <measure> - why` line in the pull request or a commit
  message says why.
- **When those levels are missing**, for a run that was cancelled or has
  expired, the check measures the base itself in a copy of it. Slower, never
  skipped. `just check` does the same locally, without the slow mutation run
  on either side.
- **`quality.json` keeps only the test suite's time budget**, a limit set by
  hand rather than a level.

## Consequences

- Merging one pull request no longer breaks the others, and nobody runs the
  ratchet to fix a number.
- **Worse:** the levels no longer show in a pull request's diff; they are in
  the checks' output and in main's runs.
- **Worse:** the check depends on GitHub keeping main's runs, 90 days by
  default; past that it measures the base, which takes longer.
- The design page's quality table is now written by hand from main's latest
  levels, not read from `quality.json`.

## Related

`scripts/ratchet.py`, the `ratchet` job in `.github/workflows/checks.yml`,
`tests/test_ratchet.py`, and claude-voice's ADR-CV-009.
