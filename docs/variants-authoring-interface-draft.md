# Native variants authoring interface

Prepared from checker main `76ec14e`, with reviewed PR21 `0f58fade` and PR23
`b615e8b` in a local uncommitted union at `work/variants-authoring`. No AC merge
is implied. Math integration remains a separate component change.

## Ownership and wire contract

`question-variants.py --stdin` is the component-owned thin executable. It finds
the installed canonical native authoring distribution and checker wheel before
importing trusted modules, rather than importing from the lesson directory.
One JSON request and one JSON response go over stdin/stdout; diagnostics go to
stderr and an error exits nonzero. No generic plugin registry is required.

Request version 1:

```json
{"version":1,"action":"resolve","source":"original exercise block","question":"question text","options":{},"projectRoot":"/course","file":"pages/lesson.qmd","label":"q-one","approval":"required","renderMode":"preview","manifest":"_variants/q-one.yml","baseHash":null}
```

`source` preserves original authored options for one native extraction path and
the hard legacy-parameters migration error. `question` is the existing Lua body;
`options` is its existing parsed option mapping, including solution/translations.
`projectRoot` and `file` resolve relative checker and manifest paths safely.
The adapter checks their consistency rather than parsing two competing sources.
`approval` is required or optional, resolved by Lua from the approved existing
`ctm-assessment.variants.approval`/`CTM_VARIANTS` design spelling. This setting is
currently missing in implementation; optional is the approved OPEN mode.
`renderMode` is review, preview or publish. Actions are resolve (read-only),
generate (append up to 25 tested distinct candidates), and decide (explicit
id/hash/status plus by/date/reason). Mutations require the previous manifest
baseHash. A file CLI uses the same operation, never a second parsing implementation.

Response version 1 contains `manifest`, `baseHash`, `records`, `deployableIds`,
`warnings`, and generation counters. Each record carries id/hash, nullable n,
status/state, resolved question/solution/options, teacherInputs, tests, and the
existing exact context:

```json
{"version":1,"fields":["answer"],"variables":{"version":1,"value":["dict",[]]},"teacher":{"version":1,"value":["dict",[["answer",["integer","2"]]]]},"variant":null}
```

For an explicitly decided candidate context.variant is exactly `{n,id,hash}`;
undecided preview uses null and retains id/hash beside context. Existing codec
does not permit n=0. Explicit optional deployment keeps null plus a proposal
`{id,hash}` sidecar and not-approved banner. Student selection uses internal
`proposal:` plus id only while n is absent; approved variants use their stable
decision n. This does not change the exact-context codec.

## Persisted history and generation

A versioned manifest retains all proposal versions, exact replay tapes, current
decision rows (the existing model schema), and append-only decision events.
Only an explicit decision allocates n, monotonically above historical numbers.
Changing source does not erase old proposals, rejected notes or decisions.
Writes use a same-directory temporary file, fsync and atomic replace, under an
exclusive short-lived lock; compare baseHash while locked to reject stale UI/bot
writes. JSON formatting is valid YAML and makes the first writer deterministic.

Replay retained approved/candidate tapes independently before traversal, classify
current/changed/moved/gone, then lazily request new accepted records. Compose the
supervised choice stream, component placeholder resolver, canonical snapshot,
and tested collector. Count only new note-distinct passing records; test errors
are errors, not resampling. Do not request a 26th accepted candidate or build a
20k unchecked pool. Preserve retained order. For new proposals, add deterministic
label-seeded per-domain traversal ordering to the supervised stream, bounded to
each finite domain rather than the Cartesian pool; keep replay tape semantics
unchanged. This is a small explicit extension to PR23, whose current DFS is not
seeded. Exhaustion and budgets are distinct reported outcomes.

B1 snapshot construction must combine ordered canonical math/operators with raw
placeholder resolutions in prose, ordered teacher fields and effective grading
semantics/checker digest. Full prose and variable names are excluded. Translation
copies must not duplicate content in identity. PR21 math_segments alone is not
sufficient. Default-language field labels are mandatory.

## Small implementation sequence and tests

1. Versioned history, optimistic atomic IO, explicit decisions and required/
   optional publish gate; focused races, stale writes, history and number tests.
2. Safe canonical native distribution producer plus script CLI; isolated import,
   reproducible archive and same engine contract tests. Browser wheel unchanged.
3. Component-native math resolver wrapper, supervised lazy orchestration and
   exact teacher/authored tests. Focused 25-more, rejection dedup, range expansion,
   canonical identity and budget/error tests. Root owns existing math Lua/JS.
4. Local review UI using same manifest API, keyboard decisions, reasons, undo and
   copy/download stale-base flow; root owns shared student variants API/storage.
5. Required sticky-comment bot in a focused commit: trusted-base decision scripts,
   same-repo write permissions, serial updates, hidden identity tokens, no PR code
   execution in privileged context, explicit downstream recheck dispatch.

Required publish/CI fails at zero approvals and warns below target. Explicit
optional permits unapproved, warns, and never deploys rejected. Review/preview
remains usable. Student restore hash→n→id, no automatic execution, save-off
session-only seed/seen, withdrawn read-only history and pools are root's bridge
scope. No production activation or broad campaign is part of these local tests.
