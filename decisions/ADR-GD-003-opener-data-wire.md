# ADR-GD-003: Read the door state from the opener's data wire, and offer it as a second way to press

## Status

Proposed. Roy asked for both, reading and sending (by voice, 2026-11-04).
The details below are a proposal for him to approve. Nothing is wired,
flashed or sent on the opener's wire until he does.

## Context

The plan kept reed contacts as the only source of door state, because the
0+2 bus was unproven on this model ("Door state from the opener itself" in
[`docs/plan.md`](../docs/plan.md)). It said to revisit that in a decision
record if the bus turned out to work. On 2026-11-04 Roy captured four whole
packets on 0+2 with an oscilloscope. Decoded with argilo's secplus
(<https://github.com/argilo/secplus>, GPL-3.0-or-later), they are Security+
2.0 wireline packets at about 4000 baud. Each is a status message (command
0x081) from the opener itself: the door state (opening, closing, stopped)
changes, and the rolling code counts up. The details are in the plan's
"Measured on Roy's opener" table.

How a controller talks back on this wire is known from ratgdo, the
open-source board that does it on US openers
(<https://github.com/ratgdo/esphome-ratgdo>, `components/ratgdo/secplus2.cpp`).
It asks for status with command 0x080. It moves the door with command 0x280
and an action (close 0, open 1, toggle 2, stop 3): a "pressed" packet, then
a "released" packet 150 ms later. It uses its own 32-bit client id and a
28-bit rolling code that only ever goes up and is saved in flash. Before
sending, it waits for the line to be idle for 1.3 ms. Its board runs at
9600 baud; this opener uses about 4000.

Not known yet:
- whether this opener obeys commands from a controller it has never seen;
- what it sends when the door is fully open (1 in ratgdo's table; not
  captured yet).

Learned since (Roy, 2026-11-04, capture T0005): while the door stands still
the opener repeats its status by itself, about every 5 minutes. Fully closed
reads 2. That is too rare for the 2 s freshness rule, so listening alone
still cannot allow a press; asking (0x080) is needed for that.

## Options considered

- **Keep the reed contacts only.** Not taken: the opener already says where
  the door is, for free, and Roy wants to use it.
- **Read the wire, press only with the relay.** The safest step, and the
  first one built. But it can't ask the opener for its state, and a status
  that is only sent at changes cannot prove it is still true.
- **Read the wire and send on it, as well as the relay.** Taken, as Roy asked.
  Each part can be switched on by itself.
- **Send on the wire only, no relay.** Not taken: the relay works with any
  opener and needs nothing from the protocol.

## Decision

The controller learns three things, each switched on in its configuration.

1. **Door state from the wire.** It reads status packets (0x081) on 0+2 and
   maps the opener's state:
   - open → open, closed → closed;
   - opening or closing → moving;
   - stopped part way, or anything else → unknown, as the reed contacts
     already report a door stopped between the ends.

   A packet that doesn't decode is ignored. **A status older than
   `status_max_age_ms` (2 s) counts as unknown**, so a press needs a fresh
   one. With the sender fitted, the controller asks for one (0x080) when a
   press is requested. Listening only, it presses only if the opener spoke
   in the last 2 s.

2. **A press can go out on the wire instead of through the relay**
   (`press_by: relay | wire`). On the wire, a press is a directional command:
   "open" sends open (1) and "close" sends close (0), never toggle. A
   mistaken press therefore can't reverse a door that was already moving.
   It is a pressed packet, then released 150 ms later. Every rule that
   holds for the relay holds for the wire: the spoken yes, state known,
   closing only from fully open, two seconds between presses, and nothing
   on its own.

3. **Only two commands are ever sent:** status (0x080) and door action
   (0x280, open or close). Never learn, pair, lock, light or any other
   command. The rolling code is saved before each send, and on boot it jumps
   ahead by a margin, so a code is never used twice. The controller waits
   for 1.3 ms of idle line before it sends.

**The relay stays the way to press** (`press_by: relay`, the default) until
pressing on the wire has passed a bench test with Roy watching (Roy,
2026-11-04). Until then, the wire is used only to read the state, and at
most to ask for it.

The secplus C code is taken in unchanged, at a fixed commit (in
`firmware/third_party/secplus/`), rather than rewritten. It is the code
ratgdo uses, and it is tested upstream.

## Consequences

- **Nothing about the reed contacts is lost.** They stay supported, and
  `state_from: reed | wire` picks one.
- **Sending on the wire puts a transistor on the opener's bus.** A fault
  there could hold the bus low, and the opener's own controls might stop
  answering. The circuit is a separate, open-drain stage, off by default.
  It is tested on the bench with Roy watching before it is ever left on.
- **The listen-only tap shares ground with the opener** (a resistor divider
  for the first test, see the plan). The finished build isolates it.
- **Worse:** an unofficial protocol. The maker can change it in a firmware
  update, and the controller then reads "unknown" and refuses. It fails
  closed, but it fails.
- Commands from an unknown controller may simply be ignored by this opener.
  If so, the relay remains the way to press.

## Related

[`docs/plan.md`](../docs/plan.md) ("Door state from the opener itself",
"Next step for 0+2", section 4); [ADR-GD-002](ADR-GD-002-close-without-photocells.md);
`firmware/door_logic/`; `hardware/pins.toml`.


**2026-11-05, measured: the opener now sends at 9600 baud.** Until about
08:30 the controller decoded the opener at 4000 baud (14 of 22 packets at
08:16). The opener was then power cycled, and from then on every packet
reached a 4000-baud UART as 8 garbled bytes starting 18/38/88/98 00, with no
framing errors. That is what a 4000-baud UART makes of a 19-byte packet sent
at 9600, and a 10 nF to 1 nF filter swap did not change it. With the UART at
9600 (10:43), whole packets decode again: closed, then opening and open
after a press, with no rolling-code gap. Why the speed was 4000 before is
not known; check it with the scope if it ever changes back.
