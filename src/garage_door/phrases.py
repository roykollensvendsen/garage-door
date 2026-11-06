# SPDX-License-Identifier: GPL-3.0-or-later
"""Magic phrases that stand in for the spoken yes (decisions/ADR-GD-008).

Each user writes their own phrases, per language, in a file outside git
(``~/.config/garage-door/phrases.toml`` by default, readable by its owner
only). With no file, the feature is off. A phrase works only for its own
action, open or close. Matching ignores case, punctuation, spacing and
accents, collapses a repeated word (speech recognition often drops one),
and forgives at most one wrong, missing or extra letter in the whole phrase,
only in a word of five letters or more. The phrase's words must all be
there, in order, next to each other.

The file looks like::

    [nb]
    open = ["sesam, lukk deg opp"]
    close = ["sesam, lukk deg igjen"]

    [en]
    open = ["open sesame now"]
"""

from __future__ import annotations

import re
import stat
import tomllib
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from garage_door.door import Action

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Mapping, Sequence

FORGIVEN_FROM_LETTERS = 5  # a word this long may have one slip


class PhraseError(ValueError):
    """The phrase file cannot be used; the server refuses to start, and says why."""


def words(text: str) -> tuple[str, ...]:
    """Lower case, accents and punctuation gone, a repeated word kept once."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    plain = plain.replace("ø", "o").replace("æ", "ae").replace("ß", "ss").replace("đ", "d")
    found = re.findall(r"[^\W_]+", plain)
    return tuple(w for i, w in enumerate(found) if i == 0 or w != found[i - 1])


def _slips(said: str, wanted: str) -> int:
    """0 if equal, 1 if one letter differs, is missing or is extra, 2 for anything more."""
    if said == wanted:
        return 0
    if len(wanted) < FORGIVEN_FROM_LETTERS or abs(len(said) - len(wanted)) > 1:
        return 2
    if len(said) == len(wanted):
        return 1 if sum(a != b for a, b in zip(said, wanted, strict=True)) == 1 else 2
    short, long_ = sorted((said, wanted), key=len)
    for i in range(len(long_)):
        if long_[:i] + long_[i + 1 :] == short:
            return 1
    return 2


def _found_in(said: Sequence[str], phrase: Sequence[str]) -> bool:
    for start in range(len(said) - len(phrase) + 1):
        window = said[start : start + len(phrase)]
        # RULE: the whole phrase must be there in order
        if sum(_slips(s, w) for s, w in zip(window, phrase, strict=True)) <= 1:
            return True
    return False


@dataclass(frozen=True)
class Phrases:
    """The user's phrases for open and close, already reduced to words."""

    by_action: Mapping[Action, tuple[tuple[str, ...], ...]]

    @classmethod
    def from_table(cls, table: Mapping[str, object]) -> Phrases:
        """Phrases from ``{language: {"open": [...], "close": [...]}}``; PhraseError if unusable."""
        found: dict[Action, list[tuple[str, ...]]] = {Action.OPEN: [], Action.CLOSE: []}
        for language, entries in table.items():
            if not isinstance(entries, dict):
                msg = f"[{language}] must hold open = [...] and close = [...]"
                raise PhraseError(msg)
            for key, listed in entries.items():
                if key not in ("open", "close") or not isinstance(listed, list):
                    msg = f"[{language}] {key}: only open and close can have phrases, as lists"
                    raise PhraseError(msg)
                for phrase in listed:
                    reduced = words(str(phrase))
                    if not reduced:
                        msg = f"[{language}] {key}: a phrase with no words"
                        raise PhraseError(msg)
                    found[Action(key)].append(reduced)
        return cls({action: tuple(listed) for action, listed in found.items()})

    def matches(self, action: Action, said: str | None) -> bool:
        """Whether `said` holds one of `action`'s phrases."""
        if not said:
            return False
        heard = words(said)
        # RULE: a phrase works only for its own action
        return any(_found_in(heard, phrase) for phrase in self.by_action.get(action, ()))


def load_phrases(path: pathlib.Path) -> Phrases | None:
    """The phrases in `path`; None when there is no file (the feature is off)."""
    if not path.exists():
        return None
    # RULE: a phrase file others can read is refused
    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        msg = f"{path} can be read by others; run chmod 600 {path}"
        raise PhraseError(msg)
    try:
        table = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        msg = f"cannot read {path}: {error}"
        raise PhraseError(msg) from None
    return Phrases.from_table(table)
