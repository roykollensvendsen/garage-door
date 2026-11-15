# One row per rule

A rule nothing catches is a rule nothing protects. `scripts/mutate.py` turns
each rule off in turn and runs the suite; a rule whose removal breaks no test
has no test. `tests/test_rules_have_evidence.py` counts the rules in the source
against the rows here, so this folder cannot fall behind.

Each row is a file of its own, named after the rule, in a folder that is the
whole path of the file it switches off. Two pull requests then only meet when
they add the same rule. `# RULE: a token works once` in
`src/garage_door/service.py` goes in
`src/garage_door/service.py/a-token-works-once.toml` here:

```toml
[[rule]]
name = "a token works once"
file = "src/garage_door/service.py"
find = 'pending, self\._pending = self\._pending, None'
replace = 'pending = self._pending'
```

`find` is a regular expression matching the single line to replace; `replace`
is what replaces it, keeping the file valid. The line's own indentation is
kept, so do not write indentation here. `replace` takes the WHOLE line, not
just the part `find` matched: a partial line breaks the file, every test fails
at import, and the rule reads "BY LUCK" instead of "KILLED". `occurrence = 2`
picks the second matching line.

A rule in `scripts/` is proven the same way, the mutation runner's own
included: the runner has loaded its code before it switches a line off, and
the suite it starts loads the switched-off file. A rule inside `repair()`, or in
any function in the runner it calls by name, could not be proven like this,
since a killed run repairs with the switched-off code;
`test_no_rule_lives_inside_repair` refuses one there.

A rule in `firmware/door_logic/` (`// RULE:`) has `suite = "firmware"`, which
builds and runs the GoogleTest suite instead of pytest. The test that must go
red is the rule's words in CamelCase, split between the TEST's suite and name:
"press is refused when ..." is `Press.IsRefusedWhen...`.
