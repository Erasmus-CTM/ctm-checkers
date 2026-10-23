# Native authoring workflow

This implementation branch combines the reviewed placeholder and lazy-choice
leaves with the native kernel. It does not activate browser variants or claim
the complete authoring workflow is finished.

`ctm_variants.history` stores schema-versioned proposal versions, decision rows
and the complete decision event chain. Proposals never allocate approval
numbers. Explicit decisions use the existing model's stable positive numbers;
old snapshots remain in the event history. Identical proposal versions are
idempotent; changing a retained version is an error.

Manifest files use UTF-8 JSON, a valid YAML subset. `load()` returns a semantic
base hash; every `write()` requires that hash (null only for a missing file).
An exclusive adjacent lock protects compare-and-replace. Temporary output is
flushed and fsynced before same-directory atomic replacement. Existing proposal
and event prefixes cannot be truncated or rewritten, even with a current lease.
A process crash can leave a lock: a human must establish the writer is gone
before removing it. This is local optimistic concurrency, not a network lock or
an authentication mechanism.

`publication()` fails required publishing with zero current approvals and warns
below the target. Explicit optional mode and nonpublishing review/preview can
show unapproved proposals with a warning. Rejected proposals do not deploy,
including changed content at a rejected locator. Changed approvals require a
new explicit decision for required publishing.

`tools/build_authoring.py --output PATH` produces a separate native-only module
directory and `native.json` containing exact file sizes and SHA256 values.
`--check` compares the full file set and bytes, rejecting unexpected
files except interpreter-generated `.pyc` files directly inside `__pycache__`
directories, which are not distribution source and can arise in supervised
children after normal use. All other extra files fail comparison.
Use a fresh destination rather than deleting
unrecognized files. Browser wheels, page scripts, and their six-file extension
contract remain unchanged. The component wrapper and umbrella installer will
consume this native directory; installation is not yet wired by this slice.

Focused checks:

```sh
python -m unittest discover -s tests -p test_variants_history.py
python -m unittest discover -s tests -p test_variants_distribution.py
```

The inherited placeholder/streaming workflows retain all assertion steps and
now follow main's explicit manual `broad testing campaign` policy. No broad
campaign is required to check these local persistence contracts. The required
bot, safe CLI, component resolution, Generate 25 more and keyboard review UI are
subsequent work in this same coherent authoring branch; no student activation is
included here.

The recording CLI now accepts `action: decide-many` with a nonempty `decisions`
list using the same `{id, hash, status, by?, date?, reason?}` selections as
`decide`. All selections must have distinct current locators. It constructs
individual retained decision events and performs one leased atomic write only
after every selection validates. A stale hash, duplicate locator, invalid later
selection or stale base rejects the whole operation without partial approvals.
This is the native bulk API; the disconnected HTML review does not yet expose it.
