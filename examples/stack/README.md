# STACK example questions

The STACK question XML of CTM Assessment has its one home here. It came from
stack-sympy's `questions/` folder at
[`f450bcd`](https://github.com/Erasmus-CTM/stack-sympy/tree/f450bcd6adbd9a6fc23462ceeae6e27d3681bce5/questions)
(consolidation step 2) and is byte for byte the same, with one change: the
example checker file `matrix-checkers.py` imports `assess_basis` from
`ctm_checkers.matrix`, its one home in ctm-checkers (stack-sympy had the same
function as `stack_sympy.basis_helper`). stack-sympy's site copies this folder
from the ctm-checkers commit it pins, without `probes/` and `supplement/`
(inputs of the golden tables only).

The golden tables (`tests/golden/stack/`, [docs/goldens.md](../../docs/goldens.md))
grade these questions; each folder keeps its own licence:

| Path | What | Licence |
|---|---|---|
| `*.xml` (but those below) | stack-sympy's own example questions, by the CTM team (each file states its licence) | CC-BY-SA-4.0 |
| `checkers.py`, `matrix-checkers.py` | stack-sympy's example checker files | AGPL-3.0-or-later |
| `determinant-one.xml`, `determinant-example-provenance.json`, `course-sources/determinant-original.qmd` | converted from math-exercise's custom-checker example | AGPL-3.0-or-later |
| `course-b-*.xml`, `course-c-nullspace.xml`, `course-examples-provenance.json`, `course-sources/uke3-excerpts.md` | derived from the course ingmat3a_ntnu (Andrey Chesnokov); not in the golden tables (course material, design §13 item 7) | CC-BY-SA-4.0 |
| `corpus/` | 35 unchanged STACK sample questions ([README](corpus/README.md), `manifest.json`, `baseline.json`) | CC-BY-SA-4.0, [COPYING.txt](corpus/COPYING.txt) |
| `corrected/` | CTM's corrected teaching copies of four corpus questions ([README](corrected/README.md)) | CC-BY-SA-4.0, [COPYING.txt](corpus/COPYING.txt) |
| `upstream/algmap-6-1.xml` | a STACK sample question (`sources.json`) | CC-BY-SA-4.0, [COPYING.txt](upstream/COPYING.txt) |
| `upstream/bodmas.xml`, `upstream/rounding-three-dp.xml` | HELM questions from STACK's library (`sources.json`) | CC-BY-NC-4.0, [HELM-COPYING.txt](upstream/HELM-COPYING.txt) |
| `probes/` | question probes of the stack-sympy audit ([README](probes/README.md)) | AGPL-3.0-or-later |
| `supplement/` | questions written for the golden tables, for rules no example reaches ([README](supplement/README.md)) | AGPL-3.0-or-later |
