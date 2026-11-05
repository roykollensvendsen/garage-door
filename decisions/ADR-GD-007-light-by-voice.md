# ADR-GD-007: Switch the opener's light by voice, over the data wire

## Status

Proposed. Roy asked for it by voice on 2026-11-05. This is the plan for him
to approve. Nothing is built, wired, flashed or sent on the opener's wire
until he does.

## Context

The controller reads the opener's light from the status on 0+2 (read only,
since 2026-11-05). [ADR-GD-003](ADR-GD-003-opener-data-wire.md) allows only
two commands ever to be sent: status (0x080) and door action (0x280). It
names the light among the commands never to send. Switching the light needs
this decision first.

What is known:
- **The command:** ratgdo (`components/ratgdo/secplus2.cpp`,
  <https://github.com/ratgdo/esphome-ratgdo>) sends the light as its own
  Security+ 2.0 command, with off, on and toggle. **The command number and
  the data layout are to be read from that source before any code is
  written,** not from memory.
- **The opener only says the light changed in a status.** It sends no status
  when the light goes out by itself; that shows only in its next 5-minute
  repeat. Asking for status (0x080) right after a command gives the result
  at once.
- **Measured on 2026-11-05 (Roy, by eye):** the door reached closed at
  20:18:10 and the light went out at about 20:21, about 2 min 50 s later.
- **Not known yet:** whether this opener (EU LM80EVF, 9600 baud on the wire)
  obeys a controller it has never seen, with its own client id and rolling
  code.

## Options considered

- **Do nothing; switch the light at the wall control.** Not taken: Roy asked
  for it.
- **A second relay across the wall control's light button.** Not taken: the
  wall control (78EV) sits on 0+2 itself and has a light button, so it is
  more than a contact (PDF p. 23, sections 26 G–I). Its button is inside
  it, with no terminal to switch.
- **The light command on 0+2, light only, no door command over the bus.**
  Proposed. It is the smallest step that also builds the sender ADR-GD-003
  already plans for status requests.

## Decision (proposed)

1. **A sender on 0+2.** An open-drain stage pulls terminal 0 towards 2
   through a series resistor, driven from a free ESP32 output. It is
   isolated by an optocoupler, so the ESP32 never shares ground with the
   opener. The part must stand the bus's idle 10–12 V with margin; a
   6N136's output (15 V maximum) is too close, so the part is to be chosen
   from what Roy has (a PC817-type optocoupler, or a 2N7000 behind one). The
   drawing, the parts list and a pin in `hardware/pins.toml` come with the
   build, generated as the rest of the wiring is. **Off at boot:** the
   output's default holds the bus released.
2. **Only three commands may ever be sent:** status (0x080), the light (off,
   on or toggle) and, later and only under ADR-GD-003's own bench test, the
   door action. Never learn, pair, lock or any other command. The rolling
   code is saved before each send and jumps ahead at boot, as ADR-GD-003
   says. The sender waits for an idle line.
3. **A bench test first, with Roy present, the light only:** a status
   request, then light on, light off. The door is never commanded over the
   bus in this step. If the opener ignores the commands, or the bus stops
   answering its own controls, the sender is unplugged and this stays
   undone.
4. **A tool `garage_light(change: on | off | toggle)`.** **No spoken yes** (Roy:
   the light cannot hurt anyone), but it is refused unless the controller is
   armed. Unarmed (test mode), it is logged and nothing is sent. Every call
   is logged with the presses. It never moves the door, and a light token
   cannot press.
5. **Read back:** after a light command the controller asks for status, and
   the tool answers with the light the opener then reports. "Light: on" in
   every answer stays "as the last status said", with its age.

## Consequences

- The sender also gives fresh status on request, which `ask_first`
  (ADR-GD-005) needs, and makes the door state known at boot within a second.
- **Worse:** a transistor on the opener's bus. A fault there could hold it
  low, and the opener's own controls might stop answering. That is why the
  stage is isolated, off at boot, and bench-tested first.
- **Worse:** an unofficial protocol and the controller's own rolling code. A
  code used twice, or an opener update, could make the opener ignore the
  controller.
- A light switched by voice without a yes can be switched by mistake. The
  cost is a light left on or off, and Roy accepted that.
- It narrows ADR-GD-003's list of commands that are never sent: the light
  moves off it. Nothing else does.

## Related

[ADR-GD-003](ADR-GD-003-opener-data-wire.md),
[ADR-GD-005](ADR-GD-005-trust-the-last-status.md), `docs/plan.md`,
`hardware/pins.toml`, `.claude/skills/liftmaster-lm80evf/`.
