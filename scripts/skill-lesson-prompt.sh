#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# A Claude Code hook (Stop): once per session, when the session changed code
# but no project skill, ask the agent whether a lesson belongs in one. It
# prints a reason and exits 2 so Claude Code gives the agent one more turn;
# a marker in .git keeps it to once per session. Installed per clone in
# .claude/settings.local.json (see AGENTS.md, "Living skills").
set -eu
input=$(cat)
session=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id","x"))')
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
marker="$root/.git/skill-lesson-asked-$session"
[ -e "$marker" ] && exit 0
changed=$(git -C "$root" status --porcelain --untracked-files=all | cut -c4-)
printf '%s\n' "$changed" | grep -qv '^\.claude/skills/' || exit 0
printf '%s\n' "$changed" | grep -q '^\.claude/skills/' && exit 0
: > "$marker"
echo "This session changed files but no project skill. If it taught anything non-obvious (a fix, a pitfall, a procedure), add it to the matching skill in .claude/skills/ now, or say in one line why there is nothing to add." >&2
exit 2
