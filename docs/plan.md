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
  for a short. A 0.5 s touch with an insulated wire is the bench test; Roy did it on 2026-11-04 and it worked (see "Measured on Roy's opener").

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
  on 2+3**. Closing therefore relies on the opener's own force-based
  reversal, exactly as it does with the remote. Roy decided on 2026-11-04
  to allow closing by voice anyway; see section 4 and
  [`decisions/ADR-GD-002`](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-002-close-without-photocells.md).
- **ESP32 Thing:** pins 25, 34, 35, 3V3, GND and VUSB are all labelled and
  broken out; headers are not soldered yet; micro-USB and the JST battery
  socket as expected.

### Door state from the opener itself

Checked 2026-11-04, because reading the state from the opener would save two
sensors. Facts from the LM80EVF manual are marked with a page. Everything
else comes from **outside the manual** and is marked with its source and
how sure it is.

| Source of state | What it can tell us | How sure |
|---|---|---|
| Terminals 6+7, warning-light output (FLA1-LED) | **Moving**, not where. About 24 V while the door moves, with a short lead before and lag after. | The manual lists the FLA1-LED on 6+7 (PDF p. 269). The FLA1-LED manual describes it (<https://manuals.easygates.co.uk/PDF/misc/chamberlain-liftmaster-fla1-led-manual.pdf>). A measurement on the related LM100EVS: <https://www.cavelab.dev/posts/garage-door-flashing-light/>. Not measured on Roy's opener. |
| 30 VDC output, max 50 mA | Nothing about the door. Switched off in standby: Roy measured about 1.1 V idle (2026-11-04). | Rating on the label and in the manual. Standby behaviour is an **inference** from a related model's manual (LM750EVGB, <https://manualmachine.com/chamberlain/lm750evgb/2593509-operation-manual>), not stated for the LM80EVF. |
| Terminals 0+2, the opener's digital bus (Security+ 2.0) | Possibly open, closed and position, the way ratgdo boards read it. | **Community reports only**, on related EU models: <https://github.com/ratgdo/esphome-ratgdo/issues/179> and <https://github.com/konnected-io/konnected-esphome/issues/128>. State reporting dropped out for some users and was later fixed upstream (April 2026, per those threads). Nobody has reported an LM80EVF. Unofficial protocol: the maker could change it. |
| 828EV internet gateway | Open/closed, through the maker's cloud. | Needs the myQ cloud, which has been closed to third parties since 2023 (<https://www.home-assistant.io/blog/2023/11/06/removal-of-myq-integration/>). **Excluded**: nothing may leave the LAN. Gateway manual: <https://cdn.shopify.com/s/files/1/0574/2601/8495/files/114-5696-000-828EV.pdf>. |
| 829EV radio receiver | No state output. | Manual: <https://manuals.easygates.co.uk/PDF/liftmaster/829ev.pdf>. |

**Decision: reed contacts stay the primary source.** They say exactly where
the door is, need nothing from the opener, and fail safe (no signal reads as
"unknown", and nothing is pressed). **Optional later:** an optocoupler on 6+7
as a third input, to see "moving" directly, including after a press from the
remote. **Not planned:** the 0+2 bus. It is unproven on this model, and
talking on the opener's bus is a bigger change than closing a contact. If an
LM80EVF report appears, revisit it in a decision record.

### Without extra sensors? (checked 2026-11-04, before buying anything)

**0+2, the 78EV wall-control input.** Community reports show ratgdo-style
boards reading door state from this pair on EU "EV" Chamberlain/LiftMaster
openers. They are wired with ratgdo's control wire on terminal 0 and its
ground on 2: an ML700EV and an LM100EVS in
<https://github.com/ratgdo/esphome-ratgdo/issues/179>. ratgdo's wiring guide
says ROW openers carry the serial line on a separate "eserial" terminal
(<https://paulwieland.github.io/ratgdo/03_wiring.html>). The catch: state
reports stopped after hours on those models. A status watchdog merged on
2026-04-23 addresses it (same issue). Not reported on an LM80EVF. Nothing I
found documents the line's voltage, and a tap is not isolated, because it
shares ground with the opener. So: measure 0–2 first, and listen before ever
transmitting. Whether this opener speaks Security+ 2.0 at all is a guess:
yellow learn button is the usual sign (ratgdo FAQ). Check the button.

**6+7 warning light plus timing.** This sees every movement, from the
remote or the wall button too, but not the direction. Force reversal flips
the direction mid-travel with the light still on. After a power cut the
position is lost until the door reaches an end that something can detect.
"Did it close?" is exactly the question it cannot answer reliably, so it is
not enough on its own.

**Next step for 0+2: decode it, listen-only.** The bit time measured on
the scope is about 126 µs, which is about 7900 baud (7812.5 or 8000 nominal). Each
message starts with a break of 2.624 ms, about 21 bit times.

*What is known about the rate.* ratgdo's ESPHome firmware opens Security+
2.0 at **9600 baud, 8N1** and Security+ 1.0 at **1200 baud, 8E1**
(`secplus2.cpp`, `secplus1.cpp` in <https://github.com/ratgdo/esphome-ratgdo>).
For Security+ 2.0 it also turns on automatic baud detection
(`enableAutoBaud`). homekit-ratgdo32 says software serial is required for
Security+ 2.0 so that it can sense and change the baud rate
(<https://github.com/ratgdo/homekit-ratgdo32>). So not everything on a
Security+ 2.0 line need run at 9600. The secplus README gives no wireline
bit rate (<https://github.com/argilo/secplus>). Its packets start with the
sync bytes 0x55 0x01 0x00 (ratgdo's receiver looks for `0x550100`).
**Nothing found so far documents a 7812-baud wall-control protocol for the
EU EV series or the 78EV.** Searched 2026-11-04.

*Check:* in 8N1 at the right rate, a 0x55 byte looks like ten pulses of one
bit each, alternating. Look for such a run in the capture. The "fairly
regular pulses" may be one.

*Decode on the scope (MSO2024).* This needs the serial decode option (DPO2COMP).
B1 → RS-232, source CH1, threshold 6 V, polarity normal (idle high), bit
rate **custom 7900** (between the two nominal rates), 8 data bits, parity
none. Then try even parity, and then 9600 to compare. The 2.6 ms break shows as one framing error (a
0x00 byte with no stop bit) at the start of each message: that marks where a
message begins. Decoded bytes
with no further framing or parity errors confirm the format. Save the
waveform to USB (CSV) as well, so it can be decoded off the scope.

*Decode on the ESP32*, through the listen-only input below, in two stages.
1. **Raw timings first, whatever the encoding:** an ESPHome
   `remote_receiver` on GPIO36 with `dump: raw`, `idle: 5ms` and
   `buffer_size` of a few kB. It logs the width of every high and low. That
   tests the 128 µs grid, and Manchester against UART, before choosing.
2. **Then bytes:** an ESPHome `uart` with only `rx_pin` (GPIO36,
   `inverted: true`), `baud_rate: 7900` and the parity that worked on the
   scope. Add a `debug:` block (`direction: RX`, `dummy_receiver: true`,
   `after: timeout: 3ms`) that logs each message in hex. The break arrives
   as a 0x00 byte with a framing error before each message; treat it as the
   message start, not as data. Try `0x55 0x01
   0x00` as the start, and decode with secplus.

*Listen-only input on the ESP32 (proposed, not in the pin plan yet).* Use a
**low-input-current optocoupler**, chosen from its datasheet. It should be
fully on at 0.5 mA or less of input current, fast enough for 20 kbit/s or
more, with an output that runs on 3.3 V. That keeps the galvanic isolation
the plan already uses for the press output.
- **Bus side.** Terminal 0 → 22 kΩ → optocoupler LED anode. LED cathode →
  terminal 2. A reverse diode (1N4148) across the LED, and a 15 V TVS diode
  from 0 to 2 at the terminals. At 12 V that is about 0.5 mA, and only while
  the line is high. That is a light load beside the bus's own pull-up. If
  the datasheet says less current is enough, use a bigger resistor. Check on
  the scope that the idle level and the edges do not change with the input
  connected.
- **ESP32 side.** Optocoupler output → **GPIO36**, with 10 kΩ to 3.3 V and
  100 pF to ground. GPIO36 is input-only, so this circuit **cannot drive the
  bus even by mistake**. Take care: some module pinouts mark GPIO36 as
  "VP". The optocoupler inverts the signal (line high → output low), so set
  the ESPHome UART `rx_pin` to `inverted: true`, and set no `tx_pin`.
- **Then decode.** Read the bytes with the bit rate and format the scope
  found, and decode them with secplus (<https://github.com/argilo/secplus>,
  GPL-3.0) or ratgdo's code. If door-state messages decode reliably over a
  few days, the state needs no extra sensors.

**Fallback sensor without long wires: VL53L1X time-of-flight at the opener
head, aimed at the trolley.** ST rates it to 4 m indoors. An ST engineer
reports about 30 cm in strong sunlight
(<https://community.st.com/t5/mems-sensors/vl53l1-ranging-instability-in-strong-ambient-light/td-p/316650>),
and daylight comes in through an open door. Shade it, and reject readings
whose range status is not valid. Test it before trusting it.

### Measured on Roy's opener (2026-11-04)

Roy measured his LM80EVF with a Fluke 87 V on DC volts, opener plugged in and
idle. Probe tips alone did not reach the contacts in the push-in terminals:
**insert a wire through the orange lever** and measure on the wire.

| What | Result | What it means |
|---|---|---|
| 1+2, push-button input, idle | **about 10 V DC** | Well under the AQY212EH's 60 V. A small PhotoMOS or relay across 1+2 is fine. |
| Joining 1+2 by hand for about 0.5 s, three times | 1st: **opened**, 2nd: **stopped**, 3rd: **closed** | Confirms one input that steps open → stop → close (manual PDF p. 24, section 27). The controller can't know what the next press will do unless it knows the state, so a press stays refused unless the door is fully open or fully closed. |
| 30 VDC output, idle | **about 1.1 V** | Switched off in the opener's under-1-watt standby, as the manual's note on standby suggests (PDF p. 23, section 26 O). Not usable as power or as a signal while idle. |
| 0+2 (78EV wall control), idle | **about 10 V DC**; after the door had run, **about 11.17 V**, and it stayed there | Powered, like 1+2. The rise is probably the opener leaving standby. The earlier 0 V reading was poor probe contact. |
| 0+2 while the door ran | DC dipped slightly, then returned to 11.17 V. Frequency mode reads **0 Hz while the door moves**. A reading appears only briefly **around each change of state**: about **285 Hz** around the start, **27.27 Hz** at a stop part-way, **17.51 Hz** when it stopped closed (hand-held probes) | **Bursts of traffic at each change of state, quiet in between**, as a bus that sends status on change (Security+ 2.0-style) would show. A multimeter cannot resolve serial data, so the figures are artefacts of the bursts, not baud rates. **Not proven** until captured. |
| 0+2 on an oscilloscope, triggered by the remote | Tektronix MSO2024, 10x probe, ground clip on 2, tip on 0, 5 V/div, 1 ms/div, falling edge at 6 V, Normal, Single. Idle **steady at about 10–12 V**. At the trigger the line drops **sharply to about 0 V and stays low for about 2–3 ms**. Then **a burst of short pulses**, pulled low and released, open-drain style | **A data line, not a plain button input.** A long low "break" and then bytes is what a Security+ 2.0-style one-wire serial bus looks like. Bits not resolved at 1 ms/div. **Bit rate and protocol not yet measured**; next capture below. |
| 0+2, pulse widths (scope cursors in the zoom window) | Idle high about 12 V. Break low for **2.624 ms**. Then high **128.4 µs**, low **254 µs**, high **252.4 µs**. After that, a run of fairly regular pulses, then longer lows and some wider highs: **504.4 µs** and **754.4 µs**. The message lasts **more than about 10 ms** | The widths are 1, 2, 2, 4 and 6 bits: 1893.6 µs over 15 bits is **about 126.2 µs per bit, about 7920 baud**. The break is about 21 bit times, a little longer than two 8N1 frames (20 bits): a classic UART break marking the start of a message. Nominal is probably **7812.5 baud** (8 MHz / 1024, 128 µs) or **8000 baud** (125 µs). Both are within about 1.3 % of the measured rate, which a UART tolerates. Either way it is **not the 9600 baud** that ratgdo uses for Security+ 2.0. It could be a variant, or another encoding (Manchester at 128 µs per half-bit is also possible). **Not decoded yet.** |
| 6+7 (warning light) | not measured yet | Measure idle and while the door moves. |

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
[`decisions/ADR-GD-001-esphome-native-api.md`](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-001-esphome-native-api.md).
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
[`decisions/deferred.md`](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/deferred.md).

**Updates and logs.**

- **USB once.** The first build goes in over the board's micro-USB socket.
  The board is identified, read-only, as an ESP32-D0WDQ6 (silicon revision
  v0.0) with a 26 MHz crystal and 4 MB of flash, on an FTDI FT231X USB
  serial chip. The firmware is told about the 26 MHz crystal; ESP-IDF
  otherwise assumes 40 MHz.
- **Over Wi-Fi after that.** Later builds go over the home network with
  ESPHome's OTA, which needs a password and is reachable from the LAN only.
- **Two app slots, with rollback.** The 4 MB flash holds two copies of the
  app. An update is written to the idle one. If it does not boot and come up
  properly, the bootloader goes back to the one that worked
  (`enable_ota_rollback` together with `safe_mode`).
- **Logs over the network.** The controller streams its log over the same
  encrypted API connection (`esphome logs`), and over USB serial when
  plugged in. No separate syslog server is needed. ESPHome's `syslog`
  component can be added if Roy wants the logs kept centrally.
- **USB stays the recovery path.** If neither slot boots, or the OTA
  password is lost, the board is reflashed over USB. So the micro-USB
  socket must stay reachable in the enclosure.

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
| Closing by voice, without photocells | Allowed (Roy, 2026-11-04). The controller presses the same input as the wall button and the remote, so the opener's force reversal works exactly as it does with them. Close is offered only from fully open, only after a spoken yes, and never repeated on its own. If the door is not fully closed after the travel time, the answer is "The garage door did NOT close, possibly reversed." Every press is logged with the state before and after. Can be switched off on the laptop (`GARAGE_DOOR_ALLOW_CLOSE=no`) or on the controller (`allow_close: "false"`). Photocells (e.g. 771EV) are recommended as a later improvement, not required. |

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
