# STACK variant backend protocol

The shared `ctm_variants.stack_component.request(payload, backend=...)` owns
history leases, decisions, numbering and publication. A backend supplies maths.
It is a context manager; exiting must retire all owned resources. `None` selects
SymPy. A native implementation provides:

| Member | Contract |
| --- | --- |
| `id` | Stable CAS/backend string, e.g. `maxima`. Must match the selected `cas`. |
| `supports_authored_tests` | Defaults to false. If false, `tests:` is rejected before generation. |
| `load_question(xml, title, options, *, authored_tests=None)` | Structural import/compilation; receives the already parsed declarations. Never silently discard options. Return backend-owned question data. |
| `seed_record(question, seed, timeout=30, *, identity=None)` | Run all candidate tests and teacher checks within the deadline. Return a shared candidate record. `identity` supplies the final `{n,id,hash}` for approval replay. |
| `propose(question, count, *, start, retained, attempt_limit, elapsed_limit, resolve_seed)` | Select candidates using the supplied verified `resolve_seed(question, seed)` callback. Return `{records, skipped, nextSeed}`. Returning unverified records is rejected. |
| `card_data(question, records, decisions, *, identifier, review, identity_verifier)` | Produce the version-2 card payload. Use `identity_verifier(question, seed, identity)` before exposing a numbered checker candidate. |
| `runtime_resources()` | Validate and return required runtime resources. Called before any history write. Failure leaves history unchanged. |

Every candidate must have `snapshot.grading.backend == data.backend == id`,
`record.id == "seed=" + seed` and `data.plan.seed == seed`. The component checks
these for retained, generated, replayed and identity-verified records. A backend
change leaves other-backend tapes unreplayed and preserves proposals/decision
history. Those decisions classify as gone/changed and cannot approve new CAS
content (variant decisions 12/20).

If authored tests are selected (decision 19), native records must include
`tests.authored = {passed: true, results: [{name, passed: true}, ...]}` in declared
order, one result per declaration. The backend runs the real grader for each
candidate; this evidence never substitutes for mathematical grading. Shared
expectation verification and candidate/name binding are described in
`docs/api.md` (`stack.test-results`).
