# SPDX-License-Identifier: GPL-3.0-or-later
"""A held folder: a folder in the temporary folder, locked while its holder runs.

The mutation runner and the quality ratchet each work in such a folder. A kill runs no
cleanup, so whoever starts next sweeps away every folder whose lock nobody holds, and
never one whose holder is still running. Copied from the voice bridge's tests (#304).
"""

import importlib.util
import os
import pathlib
import time

import pytest

ROOT = pathlib.Path(__file__).parent.parent
PREFIX = "run-"
TWO_HOURS_AGO = time.time() - 2 * 60 * 60


@pytest.fixture
def held_folder():
    spec = importlib.util.spec_from_file_location("held_folder", ROOT / "scripts/held_folder.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def let_go(folder):
    """What a killed holder leaves: the folder still there, and its lock free."""
    os.close(folder._lock)  # noqa: SLF001 - standing in for the kill
    folder._lock = None  # noqa: SLF001
    return folder.path


def test_a_held_folder_a_killed_holder_left_is_removed_by_the_next_sweep(tmp_path, held_folder):
    left = let_go(held_folder.HeldFolder(PREFIX, tmp_path))
    assert held_folder.sweep(tmp_path, PREFIX) == [left.name]
    assert not left.exists()


def test_a_held_folder_still_in_use_is_never_removed(tmp_path, held_folder):
    """Two runs at once: the one that starts second must not take the first one's files."""
    held = held_folder.HeldFolder(PREFIX, tmp_path)
    os.utime(held.path, (TWO_HOURS_AGO, TWO_HOURS_AGO))
    try:
        assert held_folder.sweep(tmp_path, PREFIX) == []
        assert held.path.is_dir()
    finally:
        held.remove()
    assert not held.path.exists()


def test_a_held_folder_with_no_lock_is_kept_for_its_grace_period(tmp_path, held_folder):
    """Made before the lock existed, or by a holder killed between making it and locking it."""
    old, new = tmp_path / f"{PREFIX}old", tmp_path / f"{PREFIX}new"
    for place in (old, new):
        place.mkdir()
        (place / (held_folder.LOCK + "-starting")).write_text("")
    os.utime(old, (TWO_HOURS_AGO, TWO_HOURS_AGO))
    held_folder.sweep(tmp_path, PREFIX)
    assert (old.exists(), new.exists()) == (False, True)


def test_a_held_folder_is_locked_before_it_is_named_as_in_use(tmp_path, held_folder, monkeypatch):
    """The lock's name never stands unlocked, so a sweep never finds one it could take."""
    flock, seen = held_folder.fcntl.flock, []

    def watched(fd, how):
        seen.append(sorted(p.name for p in next(tmp_path.iterdir()).iterdir()))
        return flock(fd, how)

    monkeypatch.setattr(held_folder.fcntl, "flock", watched)
    held = held_folder.HeldFolder(PREFIX, tmp_path)
    try:
        assert seen, "the folder was never locked"
        assert held_folder.LOCK not in seen[0]
        assert sorted(p.name for p in held.path.iterdir()) == [held_folder.LOCK]
    finally:
        held.remove()


def test_the_sweep_never_makes_a_lock(tmp_path, held_folder):
    """Opening the lock to try it must not create one in a folder whose holder is starting."""
    starting = tmp_path / f"{PREFIX}starting"
    starting.mkdir()
    held_folder.sweep(tmp_path, PREFIX)
    assert list(starting.iterdir()) == []


def test_the_sweep_leaves_links_and_other_names_alone(tmp_path, held_folder):
    other, outside = tmp_path / "pytest-of-roy", tmp_path / "outside"
    other.mkdir()
    outside.mkdir()
    (outside / "kept.txt").write_text("x")
    (tmp_path / f"{PREFIX}link").symlink_to(outside)
    for place in (other, outside):
        os.utime(place, (TWO_HOURS_AGO, TWO_HOURS_AGO))
    held_folder.sweep(tmp_path, PREFIX)
    assert other.is_dir()
    assert (tmp_path / f"{PREFIX}link").is_symlink()
    assert (outside / "kept.txt").exists()


def test_a_part_its_holder_shut_is_removed_too(tmp_path, held_folder):
    left = let_go(held_folder.HeldFolder(PREFIX, tmp_path))
    (left / "shut").mkdir()
    (left / "shut" / "inside.txt").write_text("x")
    (left / "shut").chmod(0)
    held_folder.sweep(tmp_path, PREFIX)
    assert not left.exists()


def test_removing_says_whether_the_folder_is_gone(tmp_path, held_folder):
    held = held_folder.HeldFolder(PREFIX, tmp_path)
    assert held.remove() is True
    assert held.remove() is True  # a second remove is harmless
    with held_folder.HeldFolder(PREFIX, tmp_path) as path:
        assert path.is_dir()
    assert not path.exists()


def test_the_shared_folder_the_held_folders_live_in_is_this_user_s_alone(tmp_path, held_folder, monkeypatch):
    """Someone else's folder, put there first, would see every run's files: the run stops."""
    place = held_folder.own_place(tmp_path / "garage-door-mutate-test")
    someone_else = os.getuid() + 1
    monkeypatch.setattr(held_folder.os, "getuid", lambda: someone_else)
    with pytest.raises(SystemExit, match="is not a folder only you can use"):
        held_folder.own_place(place)


def test_a_link_in_place_of_the_shared_folder_stops_the_run(tmp_path, held_folder):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "garage-door-mutate-test").symlink_to(outside)
    with pytest.raises(SystemExit, match="rm -rf -- "):
        held_folder.own_place(tmp_path / "garage-door-mutate-test")


def test_the_shared_folder_is_made_and_kept_closed_to_others(tmp_path, held_folder):
    made = held_folder.own_place(tmp_path / "new")
    assert made.stat().st_mode & 0o777 == 0o700
    older = tmp_path / "older"
    older.mkdir(mode=0o755)
    older.chmod(0o755)
    held_folder.own_place(older)
    assert older.stat().st_mode & 0o777 == 0o700
