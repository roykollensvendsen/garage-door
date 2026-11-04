# What is deliberately not done yet

A thing left undone with no trigger is a thing forgotten. Each row names what
would make it worth doing, so the question comes back on its own rather than
depending on someone remembering it. Nothing enforces a trigger; the list is
read whenever a decision record is written and when a phase ends.

| Not done | The trigger | Why not now |
|---|---|---|
| A coverage threshold in CI | Two months of measured coverage to set it below | A number picked before there is data is a guess with a gate on it |
| A code of conduct and issue templates | A second contributor, or the first outside issue | Boilerplate answering questions nobody has asked |
| A release workflow and publishing | The first release someone outside will install | A published name is claimed and a published version cannot be reused |
| `CODEOWNERS` | A second person who reviews | It would name one person as the owner of everything |
| `pre-commit` as a requirement rather than an option | A second contributor | The gates run in CI, and a hook one person installs is a hook one person maintains |
| Pressing the door from outside the home network | Roy asks to open or close the door while away | The controller cannot join the tailnet; a route in (a subnet router or an always-on box at home) is a new way in and wants its own decision |
| Branch protection and required pull requests | The repository goes public or the account gets a plan that allows protection on private repositories | GitHub refuses protection on a private repository on this plan |
| A 3D-printed enclosure: parametric OpenSCAD, with STL files built by CI and attached to releases | Roy asks for it (noted 2026-11-04), once the board and its cable glands are fixed | The parts and their layout are not settled yet; a box drawn now would be drawn twice |
