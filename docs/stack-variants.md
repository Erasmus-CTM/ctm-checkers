# STACK variants (V5)

`ctm_checkers.stack.variants` is the SymPy backend's native seed producer.
`seed_record(question, seed)` runs the real XML qtests and requires a full-mark vector on every response tree: the XML’s authored vector when supplied, otherwise the model answers. Required decimal syntax is preserved. Its neutral record carries
`seed=N`, a 16-character content hash, resolved question note, compact approval
snapshot, opaque frozen plan and actual test results. Browser grading imports
no native authoring code.

`propose` visits increasing positive seeds, deduplicates question notes, and returns tested records with bounded diagnostics. Grading and authored-test failures stop generation with the question and seed (binding variants amendment 21). Literal finite random choices provide a conservative exhaustion bound; dynamic bounds retain the time and attempt limits. Wrong-answer probes retain their actual verdicts and flag accepted answers for review.
Seeds from Moodle's `deployedseeds` are not imported or approved. Maxima owns
its generator, reference version and eventual Moodle import contract.

Approval hashes include ordered generated CASText values, canonical model
answers and effective input/PRT grading rules, backend and STACK provenance.
Handwritten prose, translations using the same placeholders, display sizing
and unused helper variables are excluded. Variable names can change without
voiding unchanged mathematical content.

Native `ctm_variants.stack_component` applies the shared leased history,
publication gate and review protocol. Every retained seed is replayed through
the real engine before use. Seed evaluation has a subprocess deadline; source,
XML and checker freshness is checked before writes. Required approval remains
the publishing default; read-only review can expose pending proposals.

STACK classification matches unambiguous content before seed locators. Stable
numbers follow content when seeds exchange values. Decision reconciliation
carries the whole mapping together; a gone historical seed may share its
locator with a different content version, distinguished by hash and stable
number. Math-exercise retains its existing locator-first semantics.

The component adapter produces payload version 2 through `card_data`. Each
variant has `{n, id, hash}`; pending review proposals have `n: null` and
`proposal: true`. Backend question and variant plan objects remain opaque to
the page controller. No Maxima runtime code is included here.
