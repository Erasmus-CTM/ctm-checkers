# Question probes of the stack-sympy audit

Small STACK questions written for the stack-sympy audit of October 2026
(ctm-assessment `docs/consolidation/stack-sympy-audit-2026-10.md`), copied
unchanged from its probes
([`q/`](https://github.com/Erasmus-CTM/ctm-assessment/tree/5c5b855b346bd98938084b6ca359ad70073b717f/docs/consolidation/stack-sympy-audit-2026-10/probes/q)
at ctm-assessment `5c5b855`). Each shows one finding at the question level
(`quiet.xml` S-04, `numabs-branch.xml` S-05, `options.xml` S-07,
`thirds.xml` S-08, `twoparts.xml` S-09, `eqtype.xml` S-10, `crash.xml` S-11,
`physics-I.xml` S-02); the golden table `stack/probe-questions` grades them
with the audit's answers (its `qprobe.py`, `crash.py` and `overflow.cjs`).
AGPL-3.0-or-later, as the audit.

Since ctm-checkers 0.7.0 (S-07) `options.xml` no longer builds: it sets two
question options the engine does not read (`complexno`, `decimals`), and
the build stops with the diagnostic that names them; its golden rows are
the import's error (`stack/probe-questions`).

Since ctm-checkers 0.8.0 (S-05) the answer `45*x` of `numabs-branch.xml`
takes the false branch of its first response node (NumAbsolute cannot be
applied to an answer that is not a number) and reaches the second node, so
the question's three question tests pass.

Since ctm-checkers 0.9.0 (S-10) the answer `2*x+1` of `eqtype.xml`
(`checkanswertype`, the teacher's answer is the equation `y=2*x+1`) is
invalid: "Your answer should be an equation, but is not."
