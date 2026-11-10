# SPDX-License-Identifier: GPL-3.0-or-later
"""Magic phrases that stand in for the spoken yes (decisions/ADR-GD-008)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from garage_door.door import Action
from garage_door.phrases import PhraseError, Phrases, load_phrases

if TYPE_CHECKING:
    import pathlib

NB_EN = {
    "nb": {"open": ["sesam, lukk deg opp"], "close": ["sesam, lukk deg igjen"]},
    "en": {"open": ["open sesame now"], "close": ["close sesame now"]},
}


def write(tmp_path: pathlib.Path, text: str, mode: int = 0o600) -> pathlib.Path:
    path = tmp_path / "phrases.toml"
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


# --- Matching -------------------------------------------------------------------


def test_a_configured_phrase_matches_in_any_of_its_languages():
    phrases = Phrases.from_table(NB_EN)
    assert phrases.matches(Action.OPEN, "Sesam, lukk deg opp!")
    assert phrases.matches(Action.OPEN, "open sesame now")
    assert phrases.matches(Action.CLOSE, "sesam lukk deg igjen")


def test_case_punctuation_spacing_and_accents_are_ignored():
    phrases = Phrases.from_table({"de": {"open": ["Sesam öffne dich bitte"]}})
    assert phrases.matches(Action.OPEN, "  sesam,   OFFNE dich... bitte ")


def test_the_phrase_may_sit_inside_what_was_said():
    phrases = Phrases.from_table(NB_EN)
    assert phrases.matches(Action.OPEN, "sesam lukk deg opp, åpne garasjedøra")


def test_one_wrong_letter_is_forgiven_only_in_words_of_five_letters_or_more():
    phrases = Phrases.from_table({"en": {"open": ["garage magic opens"]}})
    assert phrases.matches(Action.OPEN, "garaje magic opens")  # one letter off in a long word
    assert phrases.matches(Action.OPEN, "garage magik opens")  # five letters: still forgiven
    assert phrases.matches(Action.OPEN, "garage magic open")  # one letter missing
    assert not phrases.matches(Action.OPEN, "garaje magik opens")  # at most one slip in the whole phrase


def test_a_word_shorter_than_five_letters_must_be_exact():
    phrases = Phrases.from_table({"nb": {"open": ["sesam lukk deg opp"]}})
    assert not phrases.matches(Action.OPEN, "sesam lukk dag opp")
    assert not phrases.matches(Action.OPEN, "sesam lukk deg app")


def test_two_wrong_letters_in_a_word_do_not_match():
    phrases = Phrases.from_table(NB_EN)
    assert not phrases.matches(Action.OPEN, "seasm, lukk deg opp")


def test_a_repeated_word_dropped_by_speech_recognition_still_matches():
    # Roy, 2026-11-06: "sesam, sesam" came through as "sesam".
    phrases = Phrases.from_table({"nb": {"open": ["sesam, sesam, lukk deg opp"]}})
    assert phrases.matches(Action.OPEN, "sesam lukk deg opp")
    assert phrases.matches(Action.OPEN, "sesam sesam sesam lukk deg opp")


def test_the_whole_phrase_must_be_there_in_order():
    phrases = Phrases.from_table(NB_EN)
    assert not phrases.matches(Action.OPEN, "sesam lukk deg")
    assert not phrases.matches(Action.OPEN, "lukk deg opp sesam")
    assert not phrases.matches(Action.OPEN, "sesam, nå, lukk deg opp")


def test_a_phrase_works_only_for_its_own_action():
    phrases = Phrases.from_table(NB_EN)
    assert not phrases.matches(Action.CLOSE, "sesam lukk deg opp")
    assert not phrases.matches(Action.OPEN, "close sesame now")


def test_nothing_matches_without_phrases_or_without_words():
    assert not Phrases.from_table({}).matches(Action.OPEN, "sesam lukk deg opp")
    assert not Phrases.from_table(NB_EN).matches(Action.OPEN, "")
    assert not Phrases.from_table(NB_EN).matches(Action.OPEN, None)


# --- What may be configured -----------------------------------------------------


def test_any_phrase_is_allowed_even_one_word():
    # Roy, 2026-11-06: no length limit; choosing a word he does not say otherwise is up to him.
    phrases = Phrases.from_table({"nb": {"open": ["sesam"]}})
    assert phrases.matches(Action.OPEN, "sesam")
    assert phrases.matches(Action.OPEN, "Sesam, sesam!")


@pytest.mark.parametrize("phrase", ["", "  ", ", !"])
def test_a_phrase_without_words_is_refused(phrase):
    with pytest.raises(PhraseError, match="no words"):
        Phrases.from_table({"nb": {"open": [phrase]}})


def test_the_same_phrase_may_open_and_close():
    # Roy, 2026-11-06. The door's state decides the direction: a press the
    # other way is refused as "already open" or "already closed".
    phrases = Phrases.from_table({"en": {"open": ["please"], "close": ["please"]}})
    assert phrases.matches(Action.OPEN, "please open the garage")
    assert phrases.matches(Action.CLOSE, "close the garage, please")


def test_only_open_and_close_can_have_phrases():
    with pytest.raises(PhraseError, match="only open and close"):
        Phrases.from_table({"nb": {"arm": ["sesam lukk deg opp"]}})


# --- The file on Roy's machine --------------------------------------------------


def test_no_file_means_the_feature_is_off(tmp_path):
    assert load_phrases(tmp_path / "phrases.toml") is None


def test_the_file_is_read_per_language(tmp_path):
    path = write(tmp_path, '[nb]\nopen = ["sesam, lukk deg opp"]\n\n[en]\nclose = ["close sesame now"]\n')
    phrases = load_phrases(path)
    assert phrases is not None
    assert phrases.matches(Action.OPEN, "sesam lukk deg opp")
    assert phrases.matches(Action.CLOSE, "close sesame now")


def test_a_phrase_file_others_can_read_is_refused(tmp_path):
    path = write(tmp_path, '[nb]\nopen = ["sesam, lukk deg opp"]\n', mode=0o644)
    with pytest.raises(PhraseError, match="chmod 600"):
        load_phrases(path)


def test_a_broken_file_is_refused_with_its_reason(tmp_path):
    path = write(tmp_path, "[nb\nopen = \n")
    with pytest.raises(PhraseError, match="cannot read"):
        load_phrases(path)


def test_a_language_without_open_and_close_lists_is_refused():
    with pytest.raises(PhraseError, match=r"\[nb\] must hold open"):
        Phrases.from_table({"nb": ["sesam lukk deg opp"]})
