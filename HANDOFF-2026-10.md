# Handoff: Erasmus-CTM/ctm-checkers (all checker Python)

main `9e042dc` = 0.6.0 (21 Oct). Packages: `ctm_checkers.core/matrix/graph/testing/browser/math_exercise` (base wheel + page script `ctm-checkers.js`) and `ctm_checkers.stack` (separate STACK wheel + `ctm-checkers-stack.js`; math pages never load it). H2: math_exercise and stack never import each other. Python floor 3.9 (CI 3.9, 3.12, 3.13; Pyodide 0.28.3 and 0.27.2). Native STACK oracle workflow `native-stack.yml` (reusable; stack-sympy calls it at its pin). Compliance report `reports/stack-compliance/` (published by stack-sympy's site; `semantics.qmd` is the page sent to the STACK author).

## Goldens

- 9,276 rows: math 3,307 + STACK ≈5,9xx (compliance, regressions, reference, questions-project, questions-library, questions-helm [CC BY-NC, test data], questions-course [CC BY-SA, course material], probes, supplement). Recorded from the legacy code (math-exercise 8ab1b25, stack-sympy f450bcd); never regenerate from the new code.
- Tools: `tools/golden.py record/verify/update/diff`, `check-changelog` (every changed/added/removed row named in CHANGELOG; CI on PRs). Course-derived rows stay out of the other tables.
- Every grading change = a version bump (minor while 0.x) + CHANGELOG + golden diff + test + mutation tests + native agreement (STACK PHP + Maxima 5.46 at STACK 4.13.1 10d3233 / 4.14.0 3338304).

## Open at hand-off

- A set for **S-07, S-05, S-10, S-11** (§9 orders 4–7 of the step-2 design) may be open (an agent was still working at hand-off; notes in its PR bodies). **Needs independent review**, then a stack-sympy pin PR in the same set.

## Update 21 Oct, evening: STACK set S-07/S-05/S-10/S-11

- Open as ctm-checkers #10 (S-07, 0.7.0) -> #11 (S-05, 0.8.0) -> #12 (S-10, 0.9.0) -> #13 (S-11, 0.10.0), then stack-sympy #28 (pins #13's head). All target main; CI green. Needs independent review, then AC merges in that order with merge commits.
- AC's decisions: S-07 accepting `multiplicationsign` none and `matrixparens` `(` is approved; S-05's 4 rows becoming 0.7 is approved; S-10's differing nested-list message is fine; S-11 hyperbolic AlgEquiv (false here, true in STACK) is fixed later with S-12; **S-11 LowestTerms on a non-expression (false here, true in STACK) is to be discussed with AC** before any change. No force-pushes; earlier commit messages stay.

## Next work (step-2 design §9, §13 amendments)

1. Remaining STACK fixes, in order: **S-12** (deterministic budgets; `excluded.jsonl` rows become goldens), **S-04** (`quiet`), **S-08** (PRT score rounding to 3 dp, qtest replay), **S-09** (evaluate each PRT whose inputs are valid), **S-06** (plain fix: NumDecPlaces follows STACK's documented binary64 rounding; no switch). **S-03** stays unchanged until the STACK author answers (semantics page).
2. **Question tests** shared with STACK, then **H1** (after variants): `#| checker:` / `#| tests:` with `check(response, symbols)` in the STACK block; checker as its own scoring part weighted by `#| checker-value:`; library checkers into `ctm_checkers.matrix`; `#| python-checkers:`, `CHECKERS`, `checker_api` retire; `core/custom.py` arrives as the one runner (math-exercise adopts it only if its goldens stay identical).
3. Follow-ups: CI rule "STACK PRs never change math goldens and vice versa" (in `docs/consolidation-notes.md` deferred list); `simp:false` is only approximated in S-13 qtest validation; `mod(x+3,3)` qtest differs from Maxima (simplification, not printing).

## Wording rule

Public text describes only our engine. Never describe how upstream STACK handles feedback-variable or question-variable names (two private reports).

---

## Common context (same in every repo)

This file hands the remaining work to another agent (e.g. Codex). Published designs live in `Erasmus-CTM/ctm-assessment` `docs/consolidation/` (the step-5 offline/exam design and the variants design are added there by the handoff branch of ctm-assessment).

## Where things stand

| Step | State |
|---|---|
| 1 ctm-libs (shared library, ai-feedback renamed) | merged |
| 2 ctm-checkers (all checker Python in one place) | merged; STACK fix chain in progress (S-01, S-02, S-13 merged; S-07/S-05/S-10/S-11 in progress) |
| 3 pyodide-interaktiv onto ctm-libs | merged (ctm-libs #27, math-exercise #26, py-exercise #9, pyodide-interaktiv #5, ctm-assessment #22); alias removal L3x/U3c not started |
| 4 UI (reveals, modes, tab links, autosave) | phase A merged; ctm-demo migrated; final set open (ctm-libs #30 + ctm-assessment #24); ingmat3a migration waits for AC to merge `linalg-branch` into ingmat3a `main`; phases B (store/progress/quizzes/export) and C (languages) not started |
| 5 runtime + offline/exam build | designed and approved (`ctm-assessment` `docs/consolidation/2026-10-step5-offline-exam.md`), not started; December exam is a target, not a constraint |
| 6 stack-sympy onto shared runtime, packaged | not started |
| 7 grading options | not started |
| 8 PR to pyodide-interaktiv `main` | not started (AC's members decide) |
| Variants redesign | designed and approved (`ctm-assessment` `docs/consolidation/2026-10-variants.md`), not started; after the question-tests PR |

Open PRs at hand-off: ctm-libs #30 and ctm-assessment #24 (one set, see their files); a ctm-checkers + stack-sympy STACK set may appear (S-07/S-05/S-10/S-11), opened by an agent still running at hand-off. **None of these has had its independent review yet.** Review before AC merges.

## Rules (binding, from AC)

- **AC merges everything.** Agents never merge, never force-push a published branch, never create release tags. Merge commits only.
- **Merge protocol for sets** (ctm-assessment `docs/consolidation`, step-1 §12.1): a set of cross-repo PRs pins its dependencies at the reviewed PR head commits (never merge commits), carries no review-ref trailers, every branch is up to date with its base, one combined CI run tests the whole set, and AC merges it in one sitting in a stated order. Before sending: head SHAs unchanged, not behind; after merging: merge tree equals head tree.
- **Commits** are authored AND committed as `Andrey Chesnokov <aacchhee@gmail.com>`. Add a trailer naming the agent that did the work (earlier commits used `Co-Authored-By: Claude … <noreply@anthropic.com>`); keep AC's identity as author/committer.
- **Independent review** of every PR (fresh reviewer, max effort) until nothing substantive remains; CI watched until green. Reviews before every merge request to AC.
- **No code duplication across repos.** One home per piece of code (ctm-libs: runtime/UI/bootstrap/feedback; ctm-checkers: all checker Python; components keep only their own Lua/JS/CSS). Generated copies (shipped ctm-libs copy in pyodide-interaktiv, bootstrap copies) must be produced and CI-checked by script.
- **No backwards-compatibility break without AC's approval.**
- **Licence:** AGPL-3.0-or-later for code. Question XML: CTM's own CC BY-SA 4.0; STACK fixtures GPL-3.0 with notice; HELM rows CC BY-NC (test data only, labelled).
- **No HTML in Markdown authoring.**
- **ingmat3a must build green and clean** (0 warnings). Course `main` branches change only through migration PRs that AC merges.
- **Wording rule (STACK):** two upstream STACK security issues were reported privately (feedback-variable names; question-variable names with Greek letters or underscores). In anything public, describe only what our engine does ("student answers may not use question- or feedback-variable names"); never describe STACK's behaviour on this.
- **Courses:** ingmat3a is pinned to ctm-assessment `9ed46a4` until its migration PR; ctm-demo follows `ref: main`.

## Environment notes (from this session; may differ for you)

- GitHub GraphQL, codeload.github.com and jsDelivr were blocked; Actions logs could not be downloaded (read check-run annotations instead). Browser tests that need CDN files route them to local copies (see `ctm-assessment` tools and the Pyodide dist notes).
- Only Chromium ran locally; Firefox and WebKit run in CI.
- Quarto 1.8.27; Pyodide 0.28.3 (0.27.2 also tested).

## Housekeeping for AC

- Delete branches: ctm-demo `stack-repro`, `stack-notes`; ctm-assessment `diag/s10-webkit`; ctm-libs `consolidation/2026-10-step3-review`, `probe/webkit-tabs`.
- Optional: delete ctm-demo Actions artifact 12325605804 (old PR #15 build).
- STACK author: send the "semantics page updated" note once https://erasmus-ctm.github.io/stack-sympy/compliance/semantics.html#author-attention shows eight rows (it was deployed; the CDN was still serving the old page at hand-off). Second private STACK report (question-variable names) is ready in `ctm-audit-2026-10/stack/private/stack-question-variable-names.zip` if not yet sent.
- jsxgraph-quarto PR #2 (fork aacchhee/jsxgraph-quarto `audit/2026-10`, head 0b64e98) bundles 1.14.1 and is ready; paste `jsxgraph/pr2-update-1.14.1.md` into its description and send `jsxgraph/reply-2026-10-21.txt`.
