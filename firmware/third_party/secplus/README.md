<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# secplus (third party)

`secplus.c` and `secplus.h` are argilo's Security+ and Security+ 2.0
encoder and decoder, by Clayton Smith, GPL-3.0-or-later like this project:
<https://github.com/argilo/secplus>, `src/`, commit
`c35de10b1da5ad97c996402ea9ba18a65932a3cc` (2025-10-09). ratgdo uses the same
code. Get it from GitHub: the PyPI package called `secplus` is an
unrelated Windows-only C extension, not this code.

They are copied in **unchanged**, so a fix upstream can be taken by copying
again. `tests/test_third_party.py` checks the files against these hashes;
to update, copy the new files, run the firmware tests, and change the hashes
and the commit here in the same change.

| File | SHA-256 |
|---|---|
| `secplus.c` | `c0bc43928cd2919fc6de925a442bf1d03a6f0290bfe42c82172a2534a6444074` |
| `secplus.h` | `e3a7ab79723c653d592c673e1eddaf5e2de5421a04b36b66ae476b7f28f17749` |
