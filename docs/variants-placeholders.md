# Native placeholder/display primitive (partial)

`ctm_variants.placeholders.render(text, variables=None, file="<template>",
label="<question>", placeholder_timeout=5, template_timeout=30)` renders one
bounded template in an isolated native child. It reuses the existing exact
`testing.expression` evaluator, generation catalogue and literal/source guards.
It follows the [approved design §3.6a and binding amendments](https://github.com/Erasmus-CTM/ctm-assessment/blob/handoff/2026-10/docs/consolidation/2026-10-variants.md)
and [independent review findings](https://github.com/Erasmus-CTM/ctm-assessment/blob/handoff/2026-10/docs/consolidation/2026-10-variants-review.md).

- `{@expr@}` uses SymPy LaTeX. Outside math it adds `$...$`; inside math the
  placeholder's braces remain, so `\dfrac{@x-p1@}{@x-p2@}` stays a valid fraction.
- `{#expr#}` uses scalar student-input syntax: exact fractions, `^` powers,
  `abs(...)` and the imaginary constant `I`. It does not use fixture `raw()`.
- `\{@...@}` and `\{#...#}` are literal escaped markers. They are not evaluated.
- Matched inline backtick spans and backtick/tilde fenced code remain literal;
  an unclosed fence protects to the end. Unmatched backticks are ordinary text.
  This API accepts text templates only: it never substitutes checker or test code.

Math contexts include `$...$`, `$$...$$`, `\(...\)` and `\[...\]`. Dollar
boundaries follow [Pandoc's documented whitespace/digit rules](https://pandoc.org/MANUAL.html#math).
Unmatched delimiters and ordinary currency dollars remain literal; ordinary
Markdown is not rejected for them. Actual empty/nested/unclosed placeholders or
unmatched placeholder closers fail with file, exercise, line and column.

Exact finite codec-supported scalar expressions are supported. LaTeX can also
display an exact matrix. Raw matrices and other collections, strings, Booleans,
inexact values and nonfinite values are explicit unsupported errors. In particular,
the canonical codec currently has no infinity tag; this slice does not extend it.
Raw matrix/collection syntax and nonfinite display remain feature limits.
Scalar printer tests round-trip the output through the actual Math answer parser.
Free symbol names must be public identifiers and must not collide with Python
keywords/builtins or SymPy's parser namespace. Declared variable semantics that
override parser functions/constants are outside this primitive. Callers must
still declare the ordinary symbols used by their question through existing `vars`.
The existing fixture printer and all grading call sites remain unchanged.

`dispdp(value,n)` and `dispsf(value,n)` are allowed only as complete placeholder
expressions. They reuse the reviewed exact half-away-from-zero helpers, always
use a decimal point, preserve trailing zeros and never print negative zero.
`dispdp(1,2)` is `1.00`; precision is 0..1000. Significant precision is 1..1000:
fractional-place results use fixed decimal notation, and integer-place results
use an exactly n-digit mantissa (`dispsf(9.95,2)` is `1.0*10^1` in input text or
`1.0\times 10^{1}` in LaTeX). Zero prints `0` plus n−1 fractional zeros.
Display results are separate immutable `DisplayValue` objects, not exact teacher
values; arithmetic, nested display calls, use in variables and the exact context
codec reject them. Both display names are reserved in renderer input mappings.

The result has rendered `text`, `canonical_text`, ordered `resolutions` with
original character spans and exact values or display wrappers, and ordered
`math_segments`. Segment input text retains surrounding operators and duplicate
occurrences, rather than reducing placeholder values to a set. Matrix canonical
segments use the existing exact-value encoding because scalar input syntax is
unsupported. LaTeX printing is separate from these canonical input values.
This is data for a future B1 content hash; it does not implement that hash,
manifests, approvals, note deduplication, proposals, sampling or component wiring.
`math_segments` alone is insufficient: future B1 hashing must also cover ordered
raw resolutions outside math (a changed generated value in prose), the answer
keys and grading options. Do not hash the complete `canonical_text` prose: typo
fixes and translations must keep approvals. These outputs do not decide the final
cross-language hash normalization policy.

Templates are limited to 16 KiB and 128 placeholders, with 256 KiB request/output
messages and existing exact-codec limits. Per-placeholder deadlines include
startup for the first expression; the absolute template deadline never resets.
Failure discards the whole result, kills/waits for the child and joins its bounded
reader. This uses the approved trusted-author model, not a security sandbox.
All authoring code remains outside browser wheels; generated payloads do not change.
