# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller's Wi-Fi password and keys never reach the repository."""

import importlib.util
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("secret_scan", ROOT / "scripts/secret_scan.py")
assert spec
assert spec.loader
scan = importlib.util.module_from_spec(spec)
sys.modules["secret_scan"] = scan
spec.loader.exec_module(scan)


def test_git_ignores_the_secrets_and_everything_esphome_builds_from_them():
    paths = ["firmware/secrets.yaml", "firmware/.esphome/build/garage-door/src/main.cpp", "firmware/build/x"]
    result = subprocess.run(
        ["git", "check-ignore", *paths], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.stdout.split() == paths


def test_no_tracked_file_holds_a_secret_value_or_a_real_key():
    files = [ROOT / n for n in subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()]
    assert scan.findings(files) == []


def test_the_scan_catches_a_key_and_a_local_secret_value(tmp_path, monkeypatch):
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text('wifi_password: "hunter2-garage"\napi_encryption_key: "' + "Q" * 43 + '="\n')
    leak = ROOT / "work" / "leak-test.txt"  # under the repo, ignored by git
    leak.parent.mkdir(exist_ok=True)
    monkeypatch.setattr(scan, "SECRETS", secrets)
    try:
        leak.write_text("password hunter2-garage\n")
        assert scan.findings([leak]) == ["work/leak-test.txt: holds a value from firmware/secrets.yaml"]
        leak.write_text("key: " + "Z" * 43 + "=\n")
        assert scan.findings([leak]) == ["work/leak-test.txt: holds a 32-byte base64 key"]
    finally:
        leak.unlink()


def test_ci_scans_every_commit_for_secrets_and_lets_only_the_example_key_through():
    # Public since 2026-11-10: a secret deleted later is still in every clone.
    import tomllib  # noqa: PLC0415

    import yaml  # noqa: PLC0415

    job = yaml.safe_load((ROOT / ".github/workflows/checks.yml").read_text())["jobs"]["secrets"]
    checkout = next(step for step in job["steps"] if "uses" in step)
    assert checkout["with"]["fetch-depth"] == 0
    scan_step = next(step for step in job["steps"] if "gitleaks" in step.get("run", ""))
    assert "--redact" in scan_step["run"]
    assert "@sha256:" in scan_step["run"]
    allowed = tomllib.loads((ROOT / ".gitleaks.toml").read_text())["allowlists"]
    example = (ROOT / "firmware/secrets.example.yaml").read_text()
    for entry in allowed:
        assert set(entry) <= {"description", "regexes"}, "allow values, never whole files or rules"
        for value in entry["regexes"]:
            assert value.replace("\\", "") in example, f"{value} is not an example value"
