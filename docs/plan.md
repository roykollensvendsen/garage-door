# Plan: voice control of the garage door

*Status: proposed, waiting for Roy's go-ahead. Nothing has been bought, wired or
flashed. Written 2026-11-04.*

## What we are building

Roy says "open the garage". The voice session asks back "The door is closed.
Open it?", Roy says yes, and only then does a small box next to the opener
press the opener's push-button input for half a second. Two magnetic sensors
tell the system whether the door is fully open, fully closed, or somewhere in
between, so the door's state is reported before and after every press, and
nothing is pressed when the state is not known.

## 1. What the opener's terminals are for

Source: the official LiftMaster/Chamberlain assembly and operating
instructions for LM60EVF, LM80EVF, LM100EVF, LM130EVF, document 114A4C095B
(2019), 270 pages, English section plus the fold-out figure page (PDF page
269). A copy is hosted at
<https://ismartgate.com/manuals/Chamberlain_LM80EVF_manual.pdf>; the
document number on its back page identifies it as the manufacturer's own.

| Terminal | Purpose | Where the manual says so |
|---|---|---|
| **1 + 2** | Wired push button (accessory 75EV). **This is the impulse input we use.** Each short = open / stop / close in turn, like the wall button. | Figure 19–20 (button drawn on 1+2); section 19 "Press to open or close the door. Press again to stop"; diagnostic code 5-up/1-down: "Terminal 1+2 for wall control is shortened longer than 4 seconds" |
| 0 + 2 | Multi-function wall control 78EV (a data connection, not a plain contact). Not used. | Figure 19–20 |
| 2 + 3 | Photocells (771EV, 772E, G770E, 771EVK). Terminal 2 is the common for 0, 1 and 3. | Figure 19–20, photocell wiring |
| **4 + 5** | Door-in-door (wicket) contact. Ships with a wire bridge; the bridge is removed only when a wicket contact is fitted. **Leave Roy's bridge in place.** | Section 26 A: "Locate auxiliary quick connect terminals. Remove wire bridge. Insert bell wire into quick connect terminals 4 and 5"; figure 26 "4+5" |
| 6 + 7 | Flashing warning light FLA1-LED. | Section 26 B; figure 26 "6+7" |
| 30 VDC + − | Power for external devices, 30 V DC, max 50 mA. For external receivers, the "under 1 watt standby" mode must be switched off. | Section 26 O |

What the manual does **not** say, so we measure it rather than guess:

- the voltage across 1–2 when open, and the current when shorted (expected a
  low-voltage DC sense line, but not stated);
- whether 1–2 wants a plain contact or something special. The evidence says a
  plain contact: the 75EV is a simple push button, the listed key switches
  (100034, 100041) are plain contacts, and the 5-1 fault code only makes sense
  for a short. A 0.5 s touch with an insulated wire is the bench test.

Also noted: the manual says "Always use LiftMaster accessories. External
products can cause malfunctions." A contact that only closes like the 75EV
button does is the lowest-risk way to add one.

### Checked against Roy's photos (2026-11-04)

The photos are in `docs/photos/`, which git ignores.

- **Type plate:** LM80EVF, date 15-07-2021, 220–240 V, 50/60 Hz, 210 W,
  Fmax 800 N, rated load 6 Nm, KB 4 min, −30 °C to 55 °C, Chamberlain GmbH.
  This is one of the four models the manual covers.
- **Terminal block:** labelled 0, 1, 2, 2, 3, 4, 5, 6, 7 and a separate
  2-pin block "+ − OUT: 30VDC / <50mA", exactly as in the manual's figure.
  The colours match the figure's grouping too: 0 green, 1 red, 2 2 white,
  3 grey, 4 5 green, 6 black, 7 white.
- **4–5 bridge:** a black wire loop across 4 and 5, which is the factory
  bridge for the door-in-door contact. It stays.
- **Nothing else is connected.** No wall button on 1+2, and **no photocells
  on 2+3**. Closing therefore relies only on the opener's force-based
  reversal, which is why section 4 holds remote closing back until
  photocells are fitted.
- **ESP32 Thing:** pins 25, 34, 35, 3V3, GND and VUSB are all labelled and
  broken out; headers are not soldered yet; micro-USB and the JST battery
  socket as expected.

## 2. Circuit

```
   ESP32 Thing                         Opener terminal block
  ┌──────────────┐                  ┌──────────────────────┐
  │ GPIO25 ──330Ω──▶ AQY212EH LED   │                      │
  │ GND  ─────────▶  (pins 1,2)     │                      │
  │                  output 3,4 ───▶ 1                     │
  │                             ───▶ 2   (polarity free)   │
  │                                 │ 4═5 bridge: untouched│
  │ 3V3 ─10k─┬─1k── GPIO34 ◀── reed "fully closed" ── GND  │
  │          └100nF─GND                                    │
  │ 3V3 ─10k─┬─1k── GPIO35 ◀── reed "fully open"   ── GND  │
  │          └100nF─GND                                    │
  │ micro-USB ◀── 5 V USB charger (wall socket)            │
  └──────────────┘                  └──────────────────────┘
```

- **Press the button:** a PhotoMOS solid-state relay (Panasonic AQY212EH:
  60 V, 0.5 A, 5000 V isolation, AC/DC output so the polarity of 1–2 does not
  matter). Its LED is driven straight from GPIO25 through 330 Ω (≈6 mA; the
  part switches on at ≤3 mA). No coil, no click, no flyback diode, and full
  galvanic isolation from the opener. Fallback if the bench measurement shows
  more than 60 V or anything odd: a 3.3 V-triggerable one-channel relay module
  powered from the Thing's VUSB pin, contacts across 1–2.
- **Pulse length:** 500 ms, enforced on the ESP32 itself (the output switches
  itself off after 500 ms whatever the laptop asks), well under the 4 s that
  the opener treats as a stuck button.
- **Door state:** two magnetic reed contacts (the kind used on alarm
  systems), one where the door rests fully closed and one where it rests fully
  open. Each closes to ground when its magnet is near. External 10 kΩ pull-ups
  to 3.3 V, 1 kΩ series and 100 nF to ground for the long cable run, so a
  cable that picks up noise near the motor does not flicker the state.
- **Pins:** GPIO25 (output), GPIO34 and GPIO35 (inputs). None is a strapping
  pin (0, 2, 12, 15), so the board boots the same whether or not the opener is
  connected. 34 and 35 are input-only and have no internal pull-ups, which
  suits a sensor input with the external pull-ups above: firmware cannot
  drive them by mistake. GPIO32 and GPIO33 are avoided because the Thing has a
  32 kHz crystal fitted next to them (seen in Roy's photo), and 36–39 because
  the board ties them to the ADC's capacitors. GPIO5 (the on-board LED) shows
  a pulse.
- **Power:** a 5 V USB charger into the Thing's micro-USB socket, from the
  ceiling socket the opener already plugs into. Not the opener's 30 V output:
  at 50 mA it leaves little margin for the ESP32's Wi-Fi peaks, it needs the
  standby mode turned off, and a regulator there would tie the controller to
  the opener's electronics for no gain. No LiPo for now (a garage gets hot and
  cold, and the opener does not run in a power cut anyway).

| State from the two sensors | Meaning | May press? |
|---|---|---|
| closed sensor on, open sensor off | **closed** | yes, after a yes |
| open sensor on, closed sensor off | **open** | yes, after a yes |
| neither, within 30 s of a press | moving | no, wait |
| neither, longer | stopped part way, or a sensor fault | no, reported as unknown |
| both on | sensor fault | no |
| controller not answering | unknown | no |

### Parts list

| Part | Qty | Note |
|---|---|---|
| Panasonic AQY212EH PhotoMOS relay (DIP-4) | 2 | one spare |
| DIP-4 socket | 1 | so the relay can be swapped |
| Resistors 330 Ω, 1 kΩ ×2, 10 kΩ ×2 | | 1/4 W |
| Capacitors 100 nF ×2 | | ceramic |
| Reed contact, surface mount, normally open with magnet | 1 | fully-open position |
| Reed contact for garage doors (floor or heavy-duty), normally open | 1 | fully-closed position |
| Perfboard, 2-pin 5 mm screw terminals ×3, male pin headers for the Thing | | headers must be soldered on |
| Enclosure, about 100×70×40 mm, with two cable glands | 1 | mount clear of the rail and chain |
| 2-core bell wire, about 1 m | | box to terminals 1 and 2 |
| 4-core alarm cable, about 10 m | | the two reed contacts |
| 5 V 1 A USB charger and micro-USB cable | 1 | |
| Multimeter | | for the bench measurements |

## 3. Firmware and how the laptop talks to it

**Recommendation: ESPHome** over hand-written Arduino or ESP-IDF firmware.
Reasons and the options weighed are in
[`decisions/ADR-GD-001-esphome-native-api.md`](../decisions/ADR-GD-001-esphome-native-api.md).
In short: the pulse limit, the boot-with-output-off rule and the sensor
debouncing are a few lines of configuration that ESPHome has already got
right many times over, and its native API comes with encryption and a
pre-shared key out of the box.

**Link:** the laptop's MCP module talks to the ESP32 over the home LAN with
ESPHome's native API (TCP 6053), encrypted and authenticated with a 32-byte
pre-shared key (Noise protocol), using the `aioesphomeapi` Python library. No
broker, no Home Assistant, no web server on the device. OTA updates are
password-protected. The key lives in the laptop's secret store, never in the
repository.

**Reach:** the ESP32 cannot join the tailnet, so the MCP module must be on the
same LAN as the ESP32 to press anything. When Roy is away from home the tool
reports "not reachable" rather than trying another route. Making it work away
from home (a tailnet subnet router or an always-on box at home running the
module) is a later decision for Roy, listed in
[`decisions/deferred.md`](../decisions/deferred.md).

**Never on the internet:** no port forwarding, no cloud service, ESPHome's
web server and captive portal left out, and the router can block the ESP32's
address from the internet entirely.

## 4. Safety rules, and where each one is enforced

| Rule | Enforced by |
|---|---|
| Never press without Roy's spoken yes | The MCP module has two tools: `garage_request(action)` returns the current state and a one-time token valid for 30 s together with the question to read aloud; `garage_confirm(token)` presses. No single call can press. The voice session must only call confirm after Roy says yes. |
| Refuse when the state is unknown | MCP module: refuses on unknown, moving, fault or controller offline. Also refuses "open" when already open and "close" when already closed, since one press would do the opposite. |
| Log every press | MCP module appends one line per request and per press to a local log: time, who asked, state before, state after, result. Kept on the laptop. |
| Report state before and after | `garage_confirm` waits for the door to settle (or 30 s) and returns before and after. If it did not reach the expected end state, it says so. |
| A press cannot stick | ESP32: the output turns itself off after 500 ms; boots with the output off; ignores a second press within 2 s. |
| Nothing on the internet | ESPHome native API only, LAN only, encrypted and keyed; no web server. |
| The opener's own safety stays | Nothing touches the photocell input (2+3), the 4–5 bridge, or the force and obstruction reversal. Before going live Roy runs the manual's monthly reversal test (section 24: 50 mm obstacle). |
| No closing out of sight without photocells | Roy's photo shows no photocells on 2+3. Proposed: the MCP module offers **open only** until photocells (e.g. 771EV) are fitted, then enables close. Roy decides. |

## Order of work, once approved

1. Bench check at the opener (Roy, with a multimeter, door clear): voltage
   across 1–2, current with 1–2 shorted, and a 0.5 s touch with an insulated
   wire to confirm the door starts.
2. Order parts.
3. Solder the Thing's headers and the small board; test on the desk with an
   LED in place of the opener.
4. Flash ESPHome over USB, then fit at the opener and mount the reed
   contacts.
5. Write the MCP module (walking skeleton: status only, then request and
   confirm), with tests for every refusal.
6. Live test with Roy watching the door.
