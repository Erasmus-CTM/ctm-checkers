# Shared STACK expression admission (M4a)

The STACK page payload exposes `CTMCheckersStack.admission`, a synchronous,
immutable API usable without starting Pyodide or Maxima. Node can load the
same generated `ctm-checkers-stack.js` payload; browser workers can use their
existing `importScripts` path. The standalone factory and policy also ship
in the STACK wheel as `ctm_checkers/stack/admission.js` and
`admission-data.json`. The base math-exercise wheel/payload gains no STACK
code. Runtime-v3 and its release/archive formats are unchanged.

```js
const result = CTMCheckersStack.admission.admitExpression('2×π−α', {
  insertstars: 0,
  questionVariables: ['k', 'ta'],
  authorNames: ['k', 'ta', 'feedback_variable']
});
// result.status === 'admitted'
// result.normalized === result.canonical === '2*pi-alpha'
```

The caller supplies trusted author context: `questionVariables` are the
question environment keys; `authorNames` includes those keys and every PRT's
feedback variables. Those arrays default to empty only for context-free
expression comparison. A question adapter must supply its complete context.
`insertstars` is 0 or 1; malformed configuration raises `TypeError` and is an
author/integration failure. Malformed learner text returns a JSON result.

Every result contains `schema: 1`, the exact `stackCommit`, `status`,
`normalized`, `canonical`, `tree` and `feedback`. Status is `admitted`,
`invalid` or `unsupported`; rejected results have null canonical/tree.
Normalization is null if Unicode/character admission failed. A tree has
`kind`, `value` and `children`; source grouping/order, decimals, repeated
terms and identity operations survive canonical printing. The supported
syntax and 1,200-character/350-token/40-depth/100-digit bounds match the
existing Python subset. Unsupported constructs stay explicit, including
chained equations, plus/minus alternatives and unsupported insertstars modes
(the latter are configuration failures).

Admission here means **text and syntax admitted**, before CAS evaluation.
For example, `0^0` is admitted syntax and still fails Maxima/SymPy CAS
validation with the existing error. This API does not determine mathematical
validity, input type, forbidwords/allowedwords options, teacher-answer type,
preview LaTeX, grades, PRTs or question-state isolation. It preserves CTM's
bounded grammar and current text-rule approximations; it does not implement
the full STACK PHP parser or certify every STACK input option. In particular,
the grammar's existing function inventory includes author mathematical
helpers: native consumers must enforce their supported learner-call and
input-option contract before evaluating an admitted tree. No Maxima card
backend is enabled by loading this API.

The Python grader remains active and unchanged. Adapters/build producers
will adopt the shared boundary in a subsequent change with installed
component tests. Python admission is retained until those consumers prove
runtime and build conformance; this slice supplies the reusable implementation
and its evidence, without switching either existing backend silently.

`tools/stack_native/admission_data.py` generates the JSON from the pinned
STACK security/Unicode data and the existing grammar's constants and function
inventory. `--check` catches stale generation. The generated payload embeds
the exact JS/policy resources from its wheel; its existing wheel SHA and
development dependency version cover both resources. Released records stay
immutable, and no descriptor/archive layout changes are required.

`tests/stack/test_shared_admission.py` compares source and wheel resources,
plus the published payload, against Python's actual `_parse_answer` boundary.
Inputs include learner text extracted from the 6,193 frozen STACK rows,
every upstream identifier/replacement, the frozen native PHP S-13 messages,
S-01 contexts, prototype-property names, controls/Unicode, syntax bounds,
form-sensitive grouping and seeded expression/malformed-input cases. The
comparison covers status, exact message, normalized text, AST and canonical
form; it does not mistake an admission result for a golden grading verdict.
The manually gated acceptance workflow runs Node 22/24 and Chromium/Firefox/WebKit, then
publishes comparison counts and the deterministic vector digest. No server,
CAS, model or external service participates in JS admission tests.

Reproduce with:

```sh
python tools/stack_native/admission_data.py --check
pytest -q tests/stack/test_shared_admission.py
# After installing Playwright and its browsers:
CTM_ADMISSION_BROWSER=all pytest -q tests/stack/test_shared_admission.py
```

Use `CTM_CHECKERS_WHEEL` as in the normal wheel test job to test installed
wheel resources. `CTM_ADMISSION_REPORT=/path/to/results` writes audit JSON.
The default Python 3.12 source/wheel gate includes Node conformance; the
additional runtime/browser acceptance follows `docs/ci-policy.md` and does
not add an automatic compatibility matrix.
