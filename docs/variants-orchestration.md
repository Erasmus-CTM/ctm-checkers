# Native tested authoring composition

`ctm_variants.orchestration` composes the existing native execution, lazy choice,
placeholder/component resolution, real grading collector and retained history.
Components own source extraction, B1 snapshot construction, stable locator and
the `resolve(execution)` callback. The callback receives exact decoded variables
and choices, and returns the existing neutral `model.candidate`. Its data is
exactly `options`, `context`, and `teacher_inputs`; options carry the resolved
question/solution and authored declarative tests. The native seam invents no
component syntax, approval number, content identity or teacher printer.

Call `reconcile(manifest, source, resolve, max_records=..., ...)` before new
generation. It independently replays each distinct retained exact tape through
the supervised executor and runs the real teacher/authored tests again. Only a
typed unavailable-domain/unused-choice outcome or a false `require` makes that
tape absent. Execution, resolution and grading errors fail the operation, never
resample. It returns the reconciled manifest, current records, classification,
replayed and gone counts. Historical versions/decisions/events remain intact;
new content versions append after prior versions. Incidental display variables
or prose changes at the same canonical semantic identity preserve the original
retained record and approval. A new explicit decision can use current display
data if retained id/hash and ordered maths/teacher/grading content agree.

Call `generate(reconciled_manifest, source, resolve, current=current_records,
attempt_limit=..., max_source_records=..., ...)` for Generate25more. It opens one
supervised lazy choice stream, defaulting to label-seeded finite-domain order,
and one supervised grading collector. No unchecked Cartesian pool is created.
Only new, valid, actually tested and distinct resolved notes count toward 25;
all earlier notes, including rejected and superseded notes, remain reserved.
The call stops at 25 without requesting the next record. Actual exhaustion is
reported separately from hitting a resource budget, which fails. The returned
manifest appends only successfully tested additions with their exact codec
choice tapes. Current order, retained proposal order and decisions are preserved.

Both operations return copies and perform no file writes. The wrapper loads a
manifest with its semantic lease, performs the complete requested operation,
then calls `history.write` once. Any error returns no partial successful manifest
to save. Read-only resolve must not write changed reconciliation results.

Replay count, actual prefix attempts, resolved-source count and elapsed seconds
are explicit resource budgets, not candidate population limits. Supervised
execution/grading waits share the caller's remaining elapsed deadline. The
component resolver remains trusted caller code: its own expensive evaluation
must use supervised helpers such as the placeholder renderer. Boundary checks
cannot interrupt an arbitrary blocking callback; no total callback cancellation
claim is made by this composition.

`python tools/build_authoring.py --install-extension INSTALLED_CTM_CHECKERS`
materializes the canonical native-only `native-authoring/` sibling directory
inside an already installed extension. `--check` verifies its exact produced
files. This separate producer never changes the existing checker wheel, scripts,
manifest or committed six-file browser extension source. The umbrella invokes
it from an exact selected checker source ref. The math wrapper verifies
`native.json` before inserting that trusted directory for imports; an explicit
engineering `CTM_VARIANTS_NATIVE` directory can select the same format.

Focused actual-child tests cover 25 more, retained rejections/order/number
history, source range growth, incidental display changes, changed approval
snapshots, missing tapes, constraints, duplicate notes, real teacher-test and
execution errors, explicit replay budgets and worker-reader teardown. These
native results do not establish browser UI, student selection, installed course
acceptance, a complete teacher workflow or merge readiness.
