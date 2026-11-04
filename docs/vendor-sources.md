<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Manufacturer documents

The manufacturer's documents are copyrighted. They are kept locally in
`docs/vendor/`, which git ignores, and never committed. This page records
where each one came from, so anyone can fetch the same file and check that
it is the same. Our own notes, written in our own words and citing these
files by page, are in
[`.claude/skills/liftmaster-lm80evf/`](../.claude/skills/liftmaster-lm80evf/SKILL.md).

| Local file (in `docs/vendor/`) | What it is | Downloaded from | Retrieved | SHA-256 |
|---|---|---|---|---|
| `liftmaster-lm60-130evf-manual-114A4C095B.pdf` | LiftMaster/Chamberlain assembly and operating instructions for LM60EVF, LM80EVF, LM100EVF and LM130EVF. Document 114A4C095B, © 2019; figures 114A4C038E. 270 pages, 19 languages; English on PDF pages 16–29, figures on PDF page 269. | <https://ismartgate.com/manuals/Chamberlain_LM80EVF_manual.pdf> (a third party's copy; the document number and the Chamberlain GmbH back page identify it as the manufacturer's own) | 2026-11-04 | `0831e11039d52faacdd96c22ef6887d378d065c5e4361ae909bd1c276e119efb` |

To fetch it again, download the URL above into `docs/vendor/` under the
local name, then compare `sha256sum` with the table. If the hash differs,
the publisher has changed the file, and the page citations in the notes
need checking again.
