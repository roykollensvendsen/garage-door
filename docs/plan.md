# Plan: voice control of the garage door

*Status: proposed, waiting for Roy's go-ahead. Nothing has been bought, wired or
flashed. Written 2026-11-04.*

## What we are building

Roy says "open the garage". The voice session asks back "The door is closed.
Do you want me to open it?", Roy says yes, and only then does a small box next to the opener
press the opener's push-button input for half a second. The opener's own
status messages on its data wire (terminals 0+2) tell the system whether the
door is fully open, fully closed or moving, so the door's state is reported
before and after every press, and nothing is pressed when the state is not
known. There are no sensors on the door (Roy, 2026-11-06).

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

**Decision (revised, proposed in [ADR-GD-003](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-003-opener-data-wire.md)):**
the 0+2 bus works on this opener. Roy's captures decode as Security+ 2.0
status messages with the door state in them (see the measurements below).
So the controller takes its state from the wire. Reed contacts were the
first plan and were never fitted; Roy dropped them on 2026-11-06. The
controller's logic still supports them (`DoorLogic::update`, with its tests)
for anyone whose opener has no such wire. It can press through the relay or
by a command on the wire (`press_by: relay | wire`). How long a status is
trusted is set in ADR-GD-005 (6 minutes, with safeguards), and on the wire only open and close are ever sent.
The original reasoning, for the record: reed contacts say exactly where the
door is and need nothing from the opener; the bus was unproven on this model.
The optocoupler on 6+7 stays an option.

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

**Next step for 0+2: decode a whole packet, listen-only.** Decoding the saved
capture showed the true bit is about **250 µs, about 4000 baud, 8N1**. The
126 µs pulse measured by hand was the half-bit high after the break. The
message starts `55 01 00`, the Security+ 2.0 sync (see the table above). Each
message starts with a break of 2.624 ms, about 10 bit times. Where the
settings below say 7900, use **4000**. (After a power cycle on 2026-11-05
the opener sent at **9600 baud**, and has since; see the measurements.) A whole 19-byte packet takes about
48 ms, so capture at 10 ms/div.

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

*First bench test: a resistor divider (Roy's choice, 2026-11-04; not the
final build).* It loads the line least and needs no parts beyond resistors,
but it is **not isolated**: it ties the ESP32's ground to terminal 2. Power the
ESP32 from a USB power bank, not the laptop, and use the optocoupler below in
the build.
- Terminal 0 → **22 kΩ** → node A → **10 kΩ** → terminal 2 (ESP32 GND).
  Node A → **1 kΩ** → GPIO36. A **1N4148** from GPIO36 to 3V3, cathode
  (black stripe) at 3V3. **1 nF** from GPIO36 to GND (`102`; see below).
- **Why 22k alone on top** (Roy, scope, 2026-11-04). With 22 kΩ + 10 kΩ over
  10 kΩ, node A read **2.4 V mean**, too close to the ESP32's input-high
  level of 2.48 V. With the second 10 kΩ jumpered out it read **3.17 V mean**,
  min about 2.1 V, about 2.0 V peak to peak. So the line's high level is
  about **10.1 V mean**, with a 50 Hz sawtooth ripple from the opener's
  rectified supply and short spikes at each recharge. That is not data.
- Ratio 10/32 = 0.3125. Node A is 3.16 V at 10.1 V and 3.75 V at 12 V. At a
  worst-case 15 V it is 4.69 V. From about 11.5 V up, the diode conducts and
  holds GPIO36 near 3.9 V (3.3 V plus a 1N4148's 0.6 V). The current through
  it is at most 0.1 mA, limited by the 7.9 kΩ feeding it (22k ∥ 10k, plus
  1k). That is a small current, but 3.9 V is above the pin's 3.6 V maximum,
  so a **Schottky (BAT85, 1N5819) is needed for a permanent build**: it holds
  the pin near 3.55 V.
- **The ripple's low points matter more than its peaks.** If the 2.1 V
  minimum is the ripple's trough, not a spike, the pin sits below 2.48 V for
  part of every 20 ms while the line is idle. A UART can then see false
  start bits. Check on the scope at GPIO36 with the 1 nF fitted. If the
  troughs stay below 2.5 V, no plain divider fits both ends: for the ESP32,
  the ripple's span (about 6.7–13 V on the line) needs a ratio above 0.37 at
  the bottom and below 0.28 at the top. A switching input does fit: the
  6N136 below, or a ULN2803 channel (line → 10 kΩ → input, output → GPIO36
  with a 22 kΩ pull-up, inverted). Either switches on cleanly anywhere above
  a few volts.
- **The filter is 1 nF, not 10 nF.** The capacitor is fed through the 1 kΩ
  and the divider together, about 7.9 kΩ. 1 nF gives 8 µs, which removes the
  spikes and leaves a 250 µs bit square. 10 nF would give 79 µs and round
  the bits off. 1–2.2 nF is the range.
- The load is 32 kΩ, about 0.38 mA at 12 V.
- Drawn from the values in `hardware/pins.toml` (`[bench_divider]`) by
  `scripts/bench_divider.py`, with each resistor's colour bands and where to
  put the meter: [schematic](wiring/bench-divider-schematic.svg),
  [breadboard](wiring/bench-divider-breadboard.svg).
  `tests/test_bench_divider.py` checks the levels, the clamp current and the
  filter against the ESP32's limits.
- The divider does not invert the signal. Use `inverted: false` on the
  UART's `rx_pin`, or with `remote_receiver`.
- GPIO36 is input-only, not a strapping pin, and works for UART RX (through
  the GPIO matrix) and for the RMT peripheral. ESP32 errata: GPIO36 and
  GPIO39 can show a glitch of about 80 ns when the ADC or Wi-Fi power saving
  is on. Keep the ADC off that pin and set `power_save_mode: none`.

*Listen-only input for the permanent build: a 6N136 optocoupler (proposed,
from parts Roy has, 2026-11-04).* The divider above is for the first test.
For the permanent build the input should be **galvanically isolated**, like
the press output. Roy has 6N136s (a 1 Mbit/s photodiode-and-transistor
optocoupler, DIP-8), which is far faster than this 4000 baud line needs.
- **Bus side.** Terminal 0 → **10 kΩ** → pin 2 (LED anode). Pin 3 (LED
  cathode) → terminal 2. A **1N4148** across the LED, reversed (cathode on
  pin 2), protects it from reverse voltage. The LED drops about 1.5 V, so the
  current is about 1.0 mA at 11.2 V, 1.05 mA at 12 V and 1.35 mA at 15 V.
  That is the load on the bus, and only while the line is high (most of the
  time, since it idles high). It is four times the divider's load, so check
  on the scope that the idle level and the edges do not change.
- **ESP32 side.** Pin 8 (VCC) to 3V3, with **100 nF** from pin 8 to pin 5
  close to the chip. Pin 5 to GND. Pin 6 (output) → **GPIO36**, with **22 kΩ**
  to 3V3 (one element of the 22 kΩ SIL network, its common pin on 3V3). Leave
  pin 7 (base) open. GPIO36 is input-only, so this **cannot drive the bus**.
- **Margins.** The 6N136's current transfer ratio is at least about 19 %
  (datasheet, at 16 mA; it falls somewhat at low current). At 1 mA that is
  roughly 0.15–0.2 mA, and the 22 kΩ pull-up needs 0.15 mA to pull the
  output fully low. That is enough, but not by much. If the output does not
  go below about 0.8 V (the ESP32's input-low level, 0.25 × 3.3 V), put a
  second 10 kΩ in parallel with the first: 2 mA, twice the margin, twice the
  load. The datasheet rates it at 4.5–5 V, so check its operation at 3.3 V on
  the bench.
- **It inverts.** Line high → LED on → output low. Set `inverted: true` on the
  UART's `rx_pin` (the divider uses `false`). The idle line then still reads
  as a UART idle.
- **Edges.** At this pull-up the output rises in a few microseconds and falls
  in under one. Beside a 250 µs bit that is under 2 % distortion, which a
  UART tolerates. Check the output and the line together on the scope.
- **Not needed here:** the 4.7 V zeners, the 7805, the bridge rectifier and
  the 470 µF capacitors. The ESP32 stays on USB power, and the LED current is
  limited by its resistor even at 15 V.
- **Pinout (6N136, DIP-8):** 1 not connected, 2 anode, 3 cathode, 4 not
  connected, 5 GND, 6 output, 7 base, 8 VCC.
- Drawn from `[opto_input]` in `hardware/pins.toml` by `scripts/opto_input.py`:
  [schematic](wiring/opto-input-schematic.svg).

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
| 0+2, a saved capture decoded in software | MSO2024, CH1 saved as CSV, 20 ms at 0.16 µs per sample, triggered by the remote. Decoded with `scripts/decode_capture.py` (threshold 6 V). Runs after the break: a high of 128.6 µs, then every run a multiple of about **250 µs** (254, 1751, 2250, 1003 µs and so on) | The 126 µs "bit" was the **half-bit high right after the break**. The real bit is about **250 µs: about 4000 baud** (fitted 3973–3989). As **UART 8N1, idle high**, it decodes to `[break] 55 01 00 86 0E BD` and then the capture ends. **`55 01 00` is exactly the Security+ 2.0 sync that ratgdo's receiver looks for**, so this is Security+ 2.0 framing, at about 4000 baud instead of ratgdo's 9600. A Security+ 2.0 packet is 19 bytes (about 48 ms at 4000 baud), so this 20 ms capture holds only the first 6. **Next:** capture again at 10 ms/div (100 ms) to get a whole packet, and decode it with secplus. |
| 0+2, four whole packets decoded with secplus | MSO2024 at 10 ms/div (100 ms), CH1 as CSV, four captures triggered by the remote. Event order for the last three is Roy's recollection: open, close, stop. Each holds one whole 19-byte packet starting `55 01 00`, at about 3970 baud (252 µs bit) | Decoded with argilo's secplus (`decode_wireline_command`): all four are **command 0x081, status**, from one device id `0x405d056056`, so **the opener sends its own status** on 0+2. The rolling code counts up (0x2ce51, 53, 55, 58). **Only the door state changes**: closing, opening, closing, stopped (secplus codes 5, 4, 5, 3); light on, not locked in all. The decode agrees with Roy's order. **So the ESP32 can read the door state by listening on 0+2**, without magnet sensors; that changes the parts list once Roy has seen it. |
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
  │ GPIO36 ◀─1k─┬─ 22k ─────────────── 0  (data wire)      │
  │             └ 10k ─ GND ─────────── 2                  │
  │ micro-USB ◀── 5 V USB charger (wall socket)            │
  └──────────────┘                  └──────────────────────┘
```

- **Press the button:** a PhotoMOS solid-state relay (Panasonic AQY212EH:
  60 V, 0.5 A, 5000 V isolation, AC/DC output so the polarity of 1–2 does not
  matter). Its LED is driven straight from GPIO25 through 330 Ω (≈6 mA; the
  part switches on at ≤3 mA). No coil, no click, no flyback diode, and full
  galvanic isolation from the opener. **For the first door test**, Roy uses a
  relay module he already has (Songle SRD-03VDC-SL-C, 3 V coil, about
  120 mA, onboard driver, 2026-11-04): VCC to 3V3, **CTH** (the input that
  triggers on high) to GPIO25, CTL empty, COM and NO across 1–2, NC empty.
  A low or floating GPIO leaves it open, so a boot or crash cannot press.
  Bench check with the opener disconnected first (build guide, "First door
  test").
- **Pulse length:** 500 ms, enforced on the ESP32 itself (the output switches
  itself off after 500 ms whatever the laptop asks), well under the 4 s that
  the opener treats as a stuck button.
- **Door state:** the opener's own status on its data wire (0+2), heard
  through a resistor divider into GPIO36, listen-only. See "First bench
  test" and ADR-GD-003 and ADR-GD-005. No sensors on the door.
- **Pins:** GPIO25 (output) and GPIO36 (the data wire, input). Neither is a
  strapping pin (0, 2, 12, 15), so the board boots the same whether or not
  the opener is connected. 36 is input-only, so firmware cannot drive the
  opener's bus by mistake. GPIO34 and 35 are free. GPIO32 and GPIO33 are avoided because the Thing has a
  32 kHz crystal fitted next to them (seen in Roy's photo), and 36–39 because
  the board ties them to the ADC's capacitors. GPIO5 (the on-board LED) shows
  a pulse.
- **Power:** a 5 V USB charger into the Thing's micro-USB socket, from the
  ceiling socket the opener already plugs into. Not the opener's 30 V output:
  at 50 mA it leaves little margin for the ESP32's Wi-Fi peaks, it needs the
  standby mode turned off, and a regulator there would tie the controller to
  the opener's electronics for no gain. No LiPo for now (a garage gets hot and
  cold, and the opener does not run in a power cut anyway).

| The opener's last status | Meaning | May press? |
|---|---|---|
| closed, at most 6 minutes old | **closed** | yes, after a yes |
| open, at most 6 minutes old | **open** | yes, after a yes |
| opening or closing, within the travel time | moving | no, wait |
| stopped part way, or anything else | unknown | no |
| older than 6 minutes, or a damaged packet since | unknown | no |
| controller not answering | unknown | no |

### Parts list

| Part | Qty | Note |
|---|---|---|
| Panasonic AQY212EH PhotoMOS relay (DIP-4) | 2 | one spare |
| DIP-4 socket | 1 | so the relay can be swapped |
| Relay module, Songle SRD-03VDC-SL-C on a red board (Roy has one) | 1 | first door test only; the AQY212EH is for keeps |
| Resistor 330 Ω | | 1/4 W |
| Perfboard, 2-pin 5 mm screw terminal, male pin headers for the Thing | | headers must be soldered on |
| Enclosure, about 100×70×40 mm, with two cable glands | 1 | mount clear of the rail and chain |
| 2-core bell wire, about 1 m | | box to terminals 1 and 2 |
| 2-core bell wire, about 1 m | | box to terminals 0 and 2 (data wire) |
| 5 V 1 A USB charger and micro-USB cable | 1 | |
| Multimeter | | for the bench measurements |
| Listening on 0+2: resistors 22 kΩ, 10 kΩ, 1 kΩ; 1N4148 (a Schottky, BAT85 or 1N5819, for keeps); 1 nF ceramic; breadboard | | listen-only; the door state comes from here |

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
| Door state from the opener's wire | ESP32: only status packets that decode count. Open and closed map to open and closed, opening and closing to moving, and everything else (stopped part way included) to unknown. How long a status is trusted is set in [ADR-GD-005](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-005-trust-the-last-status.md): 6 minutes, with safeguards. [ADR-GD-003](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-003-opener-data-wire.md). |
| A press on the opener's wire | ESP32 (`press_by: wire`): the same refusals as the relay. Directional: open sends open and close sends close, never toggle. Only status and door-action commands are ever sent. The rolling code is saved before each send and jumps ahead at boot; the controller waits for an idle line. Off until a bench test with Roy watching. |
| Refuse when the state is unknown | MCP module: refuses on unknown, moving, fault or controller offline. Also refuses "open" when already open and "close" when already closed, since one press would do the opposite. |
| Log every press | MCP module appends one line per request and per press to a local log: time, who asked, state before, state after, result. Kept on the laptop. |
| Report state before and after | `garage_confirm` waits for the door to arrive, at most 9 s so the answer fits the voice's time ([ADR-GD-010](https://github.com/roykollensvendsen/garage-door/blob/main/decisions/ADR-GD-010-a-press-answers-in-the-voices-time.md)), and returns before and after. Still moving: "not yet confirmed", ask again. Stopped short of the end: it says so. |
| A press cannot stick | ESP32: the output turns itself off after 500 ms; boots with the output off; ignores a second press within 2 s. |
| Nothing on the internet | ESPHome native API only, LAN only, encrypted and keyed; no web server. |
| The opener's own safety stays | Nothing touches the photocell input (2+3), the 4–5 bridge, or the force and obstruction reversal. Before going live Roy runs the manual's monthly reversal test (section 24: 50 mm obstacle). |
| Closing by voice, without photocells | Allowed (Roy, 2026-11-04). The controller presses the same input as the wall button and the remote, so the opener's force reversal works exactly as it does with them. Close is offered only from fully open, only after a spoken yes, and never repeated on its own. If the door stopped short of closed, the answer is "The garage door did NOT close, possibly reversed."; if it is still moving when the answer is due, "NOT yet confirmed closed" (ADR-GD-010). Every press is logged with the state before and after. Can be switched off on the laptop (`GARAGE_DOOR_ALLOW_CLOSE=no`) or on the controller (`allow_close: "false"`). Photocells (e.g. 771EV) are recommended as a later improvement, not required. |

## Order of work, once approved

1. Bench check at the opener (Roy, with a multimeter, door clear): voltage
   across 1–2, current with 1–2 shorted, and a 0.5 s touch with an insulated
   wire to confirm the door starts.
2. Order parts.
3. Solder the Thing's headers and the small board; test on the desk with an
   LED in place of the opener.
4. Flash ESPHome over USB, then fit at the opener: 1+2 for the relay, 0+2
   for listening.
5. Write the MCP module (walking skeleton: status only, then request and
   confirm), with tests for every refusal.
6. Live test with Roy watching the door.
