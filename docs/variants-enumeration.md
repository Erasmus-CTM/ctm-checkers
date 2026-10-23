# Bounded exhaustive enumeration (partial native API)

`ctm_variants.enumeration.enumerate_exhaustive` builds on the
[native execution kernel](variants-generation.md) and the
[approved design §3.6e and binding amendments](https://github.com/Erasmus-CTM/ctm-assessment/blob/handoff/2026-10/docs/consolidation/2026-10-variants.md).
It stays outside browser wheels. No component author syntax is added.

`enumerate_exhaustive(source, variables=None, raw_path_limit=20000, file="<variables>",
label="<question>", variable_timeout=5, variant_timeout=30, exercise_timeout=30)`
returns `candidates`, `raw_paths`, `rejected` and `duplicates`. Every candidate
has exactly the `variables`, exact `choices` tape and canonical `locator` shape
returned by `execute`. Passing that tape to `execute(..., replay=tape)`
reproduces the candidate. Traversal follows finite domain order, including
dependent domains and multiple random calls in one expression. It is not the
future label-seeded proposal order.

The `raw_path_limit` resource bound counts raw terminal execution paths, including duplicate choice
positions and `require` rejections. A rejected prefix stops immediately, before
later unreachable choices, exactly as single execution does. The frontier plus
completed paths is checked before constructing child prefixes; exceeding the
resource bound fails the whole operation with an explicit unsupported-sampling error.
There is no truncated or sampled return. Individual domains retain the existing
20,000 bound. Authors may lower the raw limit but cannot raise it above 20,000.

Only structurally equal exact choice tapes are deduplicated. Boolean and integer
values remain distinct. Different tapes that compute equal final variables
remain separate candidates. Duplicate resolved notes require the future note /
placeholder layer and are not handled here. No notes, teacher answers, real
grader calls, proposal/default-25 selection, manifests or approvals are produced.

One isolated native child handles the complete traversal, amortizing imports.
It reuses the same evaluator and finite domains as `execute`. Each explored
prefix executes from fresh input variables; each statement and prefix execution
has a supervised deadline, and the independent exercise deadline never resets.
Startup is included. Failure kills and waits for the child and joins the bounded
reader; partial candidates are discarded. Errors name file, exercise and line.
IPC messages retain the kernel's 256 KiB bound, with a 32 MiB aggregate protocol
limit across the traversal. These resource limits are explicit failures.

Sampling remains a future AC decision: when a domain or the candidate space
grows, including crossing 20,000, which value-based sampled candidates and
label-seeded proposal order must remain stable, and must existing approved
tapes always remain discoverable? Does the full generator's 20,000 threshold
count raw paths or candidates after constraints and note deduplication?
The design and its review require an explicit
policy; this bounded API chooses none. Counting raw execution paths here is a
resource bound, not a definition of the future sampled candidate population.

Run `python tests/test_variants_enumeration.py`. The dedicated workflow pins
SymPy 1.13.3 on Python 3.9, 3.12 and 3.13 and runs both enumeration and existing
single-execution contracts against source and the actual unchanged browser wheel.
