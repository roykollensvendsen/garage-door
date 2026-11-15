# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: INP001 - loaded by path from scripts/mutate.py and scripts/ratchet.py, not a package
"""A folder in the temporary folder, locked for as long as its holder runs.

A kill runs no cleanup, so whatever a killed holder was working in stays behind. Each holder
therefore keeps a lock open inside its folder, and whoever starts next sweeps away every
folder of its kind whose lock nobody holds. A lock is held by an open file, not by a process
number, so a holder in another process namespace, or a reused number, never fools the sweep.
Two runs at once each sweep only what the other has let go of.

Copied from the voice bridge's `src/claude_voice/held_folder.py` (bridge #304), the reference
for this in every plugin, with one addition: `own_place`, for the fixed-name folder in the
shared temporary area that the held folders live in. `scripts/mutate.py` and
`scripts/ratchet.py` load it by path, since `scripts/` is not a package.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import stat
import tempfile
import time
from pathlib import Path

#: The lock a held folder keeps open while it is in use.
LOCK = ".in-use"
#: How old a folder with no lock must be before it counts as left by a killed holder. A guess:
#: long enough for any holder to have gone from making its folder to locking it.
GRACE_SECONDS = 60 * 60


class HeldFolder:
    """A new folder named `prefix` and some letters, locked until `remove`."""

    def __init__(self, prefix: str, place: Path) -> None:
        """Make the folder in `place` and lock it."""
        self.path = Path(tempfile.mkdtemp(prefix=prefix, dir=place))
        # Locked under another name, then renamed, so the lock's name never stands unlocked.
        starting = self.path / (LOCK + "-starting")
        self._lock: int | None = os.open(starting, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        # RULE: a held folder is locked before it is named as in use
        fcntl.flock(self._lock, fcntl.LOCK_EX)
        starting.rename(self.path / LOCK)

    def remove(self) -> bool:
        """Let go of the lock and remove the folder; say whether it is gone."""
        if self._lock is not None:
            os.close(self._lock)
            self._lock = None
        return remove(self.path)

    def __enter__(self) -> Path:
        """The folder, held until the block ends."""
        return self.path

    def __exit__(self, *_exc: object) -> None:
        """Let it go and remove it, however the block ended."""
        self.remove()


def left_behind(path: Path) -> bool:
    """Whether `path` is a held folder of this user's whose lock nobody holds."""
    try:
        found = path.lstat()  # the one look at it: a folder gone by the next is passed over
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(found.st_mode) or found.st_uid != os.getuid():
        return False  # a link is never followed, and another user's folder never touched
    try:
        # Opened, never made: a sweep that made the lock would hold a starting holder's name.
        lock = os.open(path / LOCK, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        # Made before the lock existed, or by a holder killed between making it and locking it.
        # RULE: a held folder with no lock is kept for its grace period
        return time.time() - found.st_mtime > GRACE_SECONDS
    except OSError:
        return False
    try:
        # RULE: a held folder still in use is never removed
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    finally:
        os.close(lock)
    return True


def sweep(place: Path, prefix: str) -> list[str]:
    """Remove every folder in `place` named `prefix`... whose holder is gone; name each one."""
    removed = []
    for path in sorted(place.glob(prefix + "*")):
        # RULE: a held folder a killed holder left is removed by the next sweep
        if left_behind(path):
            remove(path)
            removed.append(path.name)
    return removed


def remove(folder: Path) -> bool:
    """Delete a folder, giving back the rights to any part its holder shut; say whether it is gone."""
    for place, folders, _ in os.walk(folder):  # os.walk follows no link
        for name in folders:
            inner = Path(place) / name
            if not inner.is_symlink():
                with contextlib.suppress(OSError):
                    inner.chmod(inner.stat().st_mode | stat.S_IRWXU)
    shutil.rmtree(folder, ignore_errors=True)
    return not folder.exists()


def own_place(place: Path) -> Path:
    """Make `place`, or check the one there: a real folder of this user's, open to no one else.

    The held folders live in a folder with a fixed name in the shared temporary area, where
    another user could have put a link or a folder of theirs first. It is opened without
    following a link and checked through what was opened, so it cannot be swapped in between.
    A folder of this user's that others may only read, from before this check, is closed to
    them; one they can write to is refused, as they may already have put something in it.
    """
    with contextlib.suppress(FileExistsError):
        place.mkdir(mode=0o700)
    try:
        opened = os.open(place, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as e:
        raise SystemExit(_not_ours(place, f"it cannot be opened as a folder ({e.strerror})")) from None
    try:
        found = os.fstat(opened)
        # RULE: the shared folder the held folders live in is this user's alone
        if found.st_uid != os.getuid():
            raise SystemExit(_not_ours(place, f"it belongs to user {found.st_uid}"))
        # RULE: a shared folder others can write to stops the run
        if found.st_mode & 0o022:
            raise SystemExit(_not_ours(place, "others can write to it, and may already have"))
        if found.st_mode & 0o077:
            # RULE: a shared folder others may only read is closed to them
            os.fchmod(opened, 0o700)
    finally:
        os.close(opened)
    return place


def _not_ours(place: Path, why: str) -> str:
    return (
        f"{place} is not a folder only you can use: {why}. Nothing was run. Look at what it is, "
        f"remove it if it is not yours to keep (rm -rf -- {place}), and run this again."
    )
