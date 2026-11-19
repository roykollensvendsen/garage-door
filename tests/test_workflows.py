# SPDX-License-Identifier: GPL-3.0-or-later
"""A newer push stops a pull request's stale run; every other run goes to the end."""

import pathlib

ROOT = pathlib.Path(__file__).parent.parent
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))

# One group per pull request, so its next push cancels the run it superseded.
# Every other run is a group of its own, so GitHub never drops one that waits.
SUPERSEDED = (
    "concurrency:\n"
    "  group: ${{ github.workflow }}-"
    "${{ github.event_name == 'pull_request' && github.ref || github.run_id }}\n"
    "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n"
)


def test_there_are_workflows_to_check():
    assert any("\n  pull_request:" in w.read_text(encoding="utf-8") for w in WORKFLOWS)


def test_every_pull_request_workflow_cancels_only_a_pull_requests_stale_run():
    missing = [
        w.name
        for w in WORKFLOWS
        if "\n  pull_request:" in (t := w.read_text(encoding="utf-8")) and SUPERSEDED not in t
    ]
    assert not missing, f"needs the concurrency block exactly: {missing}"


def test_no_workflow_cancels_a_run_on_main():
    assert not [w.name for w in WORKFLOWS if "cancel-in-progress: true" in w.read_text(encoding="utf-8")]
