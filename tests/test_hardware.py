# SPDX-License-Identifier: GPL-3.0-or-later
"""The wiring is decided once, in hardware/pins.toml, and everything else agrees with it.

The firmware, the schematic, the wiring diagram and the pictures in the docs
are each checked against the pin plan, so a pin changed in one place and not
the others fails here instead of at the garage.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
import tomllib

import yaml

ROOT = pathlib.Path(__file__).parent.parent
PLAN = tomllib.loads((ROOT / "hardware/pins.toml").read_text())
GPIO = PLAN["gpio"]


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


class _Secret(str):
    """Stands in for ESPHome's `!secret` values, which these tests never need."""

    __slots__ = ()


def _esphome_config() -> dict:
    loader = type("Loader", (yaml.SafeLoader,), {})
    loader.add_constructor("!secret", lambda _loader, node: _Secret(node.value))
    return yaml.load((ROOT / "firmware/garage-door.yaml").read_text(), Loader=loader)  # noqa: S506


def test_the_firmware_uses_the_planned_pins():
    config = _esphome_config()
    outputs = {o["id"]: o["pin"]["number"] for o in config["output"]}
    sensors = {s["id"]: s["pin"]["number"] for s in config["binary_sensor"]}
    assert outputs["press_output"] == f"GPIO{GPIO['press']}"
    assert sensors["at_closed"] == f"GPIO{GPIO['sensor_closed']}"
    assert sensors["at_open"] == f"GPIO{GPIO['sensor_open']}"


def test_the_firmware_listens_on_the_planned_wire_pin_and_never_sends_on_it():
    # Sending on the opener's wire waits for Roy's approval (decisions/ADR-GD-003).
    uart = _esphome_config()["uart"]
    uarts = uart if isinstance(uart, list) else [uart]
    assert [u["rx_pin"]["number"] for u in uarts] == [f"GPIO{GPIO['wire_rx']}"]
    assert all("tx_pin" not in u for u in uarts)
    assert 34 <= GPIO["wire_rx"] <= 39, "an input-only pin cannot drive the opener's bus by mistake"


def test_the_controller_starts_unarmed_after_every_boot():
    switches = {s["id"]: s for s in _esphome_config()["switch"]}
    assert switches["armed"]["restore_mode"] == "ALWAYS_OFF"


def test_the_sensor_pins_are_input_only_and_need_the_planned_pull_ups():
    # GPIO 34-39 have no internal pull-up, so the firmware must not ask for one
    # and the board must carry the external ones the plan lists.
    config = _esphome_config()
    for sensor in config["binary_sensor"]:
        assert sensor["pin"]["mode"] == "INPUT"
    assert PLAN["parts"]["pull_up"]


def test_the_press_pin_is_not_a_strapping_pin():
    # 0, 2, 12 and 15 decide how the chip boots; driving them can stop it starting.
    assert GPIO["press"] not in {0, 2, 12, 15}
    assert GPIO["press"] < 34, "34-39 are input-only and cannot drive the relay"


def test_the_schematic_is_generated_from_the_current_pin_plan():
    schematic = _script("schematic")
    for path, text in schematic.outputs(PLAN).items():
        assert path.read_text() == text, f"{path.name} is stale: run python scripts/schematic.py"


def test_the_schematic_connects_the_planned_pins():
    schematic = _script("schematic")
    nets = {}
    for part in schematic.parts_from(PLAN):
        for pin, net in part.nets.items():
            nets.setdefault(net, set()).add(f"{part.reference}.{pin}")
    assert f"J1.{GPIO['press']}" in nets[f"GPIO{GPIO['press']}"]
    assert f"J1.{GPIO['sensor_closed']}" in nets[f"GPIO{GPIO['sensor_closed']}"]
    assert f"J1.{GPIO['sensor_open']}" in nets[f"GPIO{GPIO['sensor_open']}"]
    assert nets["OPENER_1"] >= {"U1.4", "J5.1"}
    assert nets["OPENER_2"] >= {"U1.3", "J5.2"}
    # The opener side touches only the relay's isolated output, nothing else.
    assert {n.split(".")[0] for n in nets["OPENER_1"] | nets["OPENER_2"]} == {"U1", "J2", "J5"}


def test_the_wiring_diagram_names_the_planned_pins_and_terminals():
    harness = yaml.safe_load((ROOT / "hardware/harness.yaml").read_text())
    connectors = harness["connectors"]
    assert connectors["OPENER"]["pins"] == PLAN["opener"]["terminals"]
    assert f"GPIO{GPIO['sensor_closed']}" in connectors["J3"]["pinlabels"][0]
    assert f"GPIO{GPIO['sensor_open']}" in connectors["J4"]["pinlabels"][0]
    assert "4-5 bridge" in connectors["OPENER"]["notes"]


def test_the_pictures_were_rendered_from_the_current_sources():
    recorded = (ROOT / "docs/wiring/sources.sha256").read_text()
    assert recorded == _script("diagram_sources").manifest(), (
        "a wiring source changed since the pictures were drawn: run sh scripts/render-diagrams.sh"
    )


def test_every_picture_the_docs_show_exists():
    for page in (ROOT / "docs").rglob("*.md"):
        for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", page.read_text()):
            if not target.startswith("http"):
                assert (page.parent / target).exists(), f"{page.name} shows a missing picture: {target}"


def test_the_relay_polarity_is_set_in_one_place_and_defaults_to_active_high():
    # Roy's first-test relay module may trigger on a low input (2026-11-04). The
    # level is one substitution, so "off" means relay open whichever module is
    # fitted; the bench check in the build guide decides it before the opener.
    raw = _esphome_config()
    assert raw["substitutions"]["relay_active_low"] == "false"
    press = next(o for o in raw["output"] if o["id"] == "press_output")
    assert press["pin"] == {"number": f"GPIO{GPIO['press']}", "inverted": "${relay_active_low}"}


def test_the_press_output_never_restores_an_on_state():
    # A gpio output starts off at boot; nothing may hold it on across a restart.
    press = next(o for o in _esphome_config()["output"] if o["id"] == "press_output")
    assert "restore_mode" not in press
    assert "power_supply" not in press


def test_ota_updates_use_the_api_key_not_a_second_one():
    # ESPHome 2026.10 refuses an OTA key that differs from the API key; the
    # example secrets used one key for both, so CI never saw it (Roy's flash).
    ota = _esphome_config()["ota"][0]
    assert "encryption" not in ota
    assert "ota_encryption_key" not in (ROOT / "firmware/secrets.example.yaml").read_text()
