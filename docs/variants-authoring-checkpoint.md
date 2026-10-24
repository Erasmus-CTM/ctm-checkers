# Authoring checkpoint — partial, do not merge

AC requested a durable stop checkpoint. No new tests or implementation were
started after that request. No browser campaign, source activation, main change
or merge is authorized by this checkpoint.

The first saved commit is `9a5bab0fd5bcdd690df655703d7e0d1939e37331`, exact tree
`97d86387dc34239d5894274a4767b2d106e96166`, with ordered parents main `76ec14e`,
reviewed placeholder PR21 `0f58fade`, and lazy stream PR23 `b615e8b`. Connector
readback verified author Andrey Chesnokov and all parents/tree. These dependency
parents do not imply that AC has merged PR21 or PR23.

That first slice has 14 existing model contracts, four new history contracts and
two distribution contracts passing. One distribution test imports its produced
directory and performs actual supervised generation, placeholder rendering and
real teacher validation, then checks the produced directory after use. Root
independently reviewed the partial source and ran its focused contracts. The
native producer keeps browser wheels/scripts unchanged. Interpreter bytecode
caches alone are excluded from the native source comparison.

This WIP successor preserves all meaningful next-slice files:

- Optional seeded lazy DFS, preserving unseeded behavior. Deterministic affine
  permutations visit each finite domain without creating a Cartesian pool.
  One new actual-child test passed: reproducible label order, different-label
  order, complete 12-path coverage, and exact tape replay. The entire preexisting
  streaming suite has **not** been rerun against this extension.
- A safe isolated file CLI and a manifest recording adapter; two focused tests
  passed including a lesson directory with spaces and hostile `math.py` and
  `json.py`, stale writes, path escape, and HTML escaping. The adapter requires
  component-resolved current records; history alone cannot establish current or
  gone source state. It never executes source in the decision-recording path.
- A disconnected keyboard review prototype that downloads a leased decision
  request. It does not save directly. It is English-only and incomplete: no
  connected helper, generation, actual student preview, bulk decision/undo,
  localization, full browser/accessibility validation or bot integration yet.
- The native distribution producer now copies the CLI launcher as well. This
  final launcher-inclusion delta has **not** had its distribution contracts
  rerun since it was added. The earlier produced-directory proof applies to
  the first slice, not a claim of final distribution closure.

`variants-authoring-interface-draft.md` preserves the agreed `--stdin` proposal.
It describes intended pipeline behavior, not completed code. The native math
resolver/wrapper `question-variants.py`, Generate 25 more orchestration, B1
component identity construction, seeded retained-tape reconciliation, canonical
umbrella installation, required bot and complete review UI remain to implement.
Root owns existing math Lua/JS and shared student runtime integration. Optional
unnumbered proposals retain exact context.variant null, proposal sidecar id/hash,
and a visible unapproved warning; they must never receive counterfeit numbers.

Resume with focused contracts only. Preserve original approved/candidate order,
all rejected notes and decision events; count 25 valid distinct tested new
records, never silently resample a failed test or generate an unchecked 20k
pool. Publish defaults required; explicit OPEN is the existing `optional`
spelling. Bot remains required. No merge readiness or complete variants feature
claim follows from this partial checkpoint. AC alone merges.
