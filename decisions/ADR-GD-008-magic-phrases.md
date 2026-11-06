# ADR-GD-008: A magic phrase stands in for the spoken yes

## Status

Accepted. Roy, 2026-11-06: he asked for it by voice, then confirmed it
directly in this session: "Jeg vil ha magiske ord både for åpning og
lukking". On the length limit he chose "Ingen grense" (no limit).

## Context

Every press by name takes two steps: a question, then Roy's spoken yes
(the plan, rule 1 of `AGENTS.md`). Over the voice that is slow, and the
question is easy to miss. Roy is usually outside the car, looking at the
door. The opener reverses on force (manual; there are no photocells,
[ADR-GD-002](ADR-GD-002-close-without-photocells.md)). The project is open
source, so others will use it in their own languages.

The words reach the server like this: the phone's speech recognition
turns speech into text, the Claude app's model reads it and calls the
tool, and this server checks what it is given. The server cannot hear Roy.

## Options considered

- **Keep the yes for every press.** Not taken: Roy asked for this.
- **Phrases for open only, the yes kept for close.** This was recommended,
  because closing without photocells is the riskier direction. Roy chose
  both.
- **A minimum length (2 words, 10 letters) against everyday words.**
  Proposed and not taken: Roy chose no limit, so choosing a phrase he does
  not otherwise say is up to the user.
- **The model decides whether the phrase was said.** Not taken: the list
  stays on the user's machine and the server matches it.

## Decision

`garage_request(action, phrase)` presses at once, with no question, when
`phrase` holds one of the user's phrases for that action. Anything else
asks the usual question.

- **Off until configured.** The phrases are in
  `~/.config/garage-door/phrases.toml` (or `GARAGE_DOOR_PHRASES`), outside
  git, per language. The server refuses to start if others can read the
  file. There is no default phrase.
- **Matching.** Case, punctuation, spacing and accents are ignored. A
  repeated word counts once, because speech recognition drops repeats.
  Across the whole phrase, one wrong, missing or extra letter is forgiven,
  and only in a word of five letters or more. The words must all be there,
  in order. Languages are not translated: each phrase the user says must
  be listed.
- **Open and close only.** Status, the light, the manual press, arming and
  manual mode are unchanged.
- **Every other rule still holds:** the door state known, not already
  there, closing allowed on this laptop, armed (otherwise test mode), the
  controller's own 2 s between presses and its refusals. The log records
  `by: phrase` or `by: yes`, never the phrase.
- **The voice is told** to pass only words Roy said in this request, and
  never to make up, complete, repeat or read out a phrase.

## Consequences

- One sentence opens or closes the door.
- **Worse:** the yes was a second, deliberate act. Now the phrase is the
  only one, and the server trusts the model to pass on only what Roy said.
  A model that repeats the phrase from earlier in the conversation, or
  picks it up from something it reads, can press. The instructions forbid
  it, but the server cannot check it.
- **Worse:** the phrase is not a password. Speech recognition and the
  voice model both see it as text. It is a deliberate code word.
- **Worse:** a short or everyday phrase can press by accident, and Roy
  chose not to limit that.
- Closing by phrase relies on the opener's force reversal alone, as
  closing by yes already does.

## Related

`src/garage_door/phrases.py`, `src/garage_door/service.py`,
`src/garage_door/server.py`, `docs/build-guide.md` ("Magic phrases"),
[ADR-GD-002](ADR-GD-002-close-without-photocells.md).
