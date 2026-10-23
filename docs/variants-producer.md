# Trusted records and sticky workflow glue — inactive

This source slice connects the native resolver, actual canonical review HTML,
neutral artifact and privileged sticky/decision adapters. Tests use fake AST,
resolver and GitHub transports; **no PR author code, live comment or dispatch was
executed to validate this slice**. Templates remain outside `.github/workflows`.
No merge, deployment, tag, workflow activation or completed day-one bot is claimed.

## Producer and check

The native-only `ctm-variants-artifact.py` launcher runs from a trusted checkout.
`templates/ctm-variants-records.py` is its course entrypoint. The records template
checks out protected default code and authored PR source into separate sibling
directories, with read permissions and no persisted Git credentials. Metadata
checks prove the source's exact current PR head, event/dispatch expected head and
the API-observed exact default SHA of the producer checkout. Fork PRs can run the
unprivileged check; privileged sticky/decide jobs reject forks.

The trusted configuration is `.github/ctm-variants.json`:

- `sourceGlobs` defines reviewed coverage, not a frozen list of question names.
  New files and labels under those globs are discovered automatically. Default
  coverage is `**/*.qmd`, excluding installed/generated directories. The course
  maintainer owns changes to discovery coverage; narrower globs must include all
  authored variant locations. Discovery is bounded to 1,000 files/250 questions.
- `wrapper` names the installed trusted math component wrapper. Its canonical
  option parser and CommonMark/Pandoc block AST are used; authored project filters
  are not loaded for discovery. Native STACK producer blocks currently fail
  explicitly instead of being silently omitted.
- `previewBase` is the actual public review-directory URL, supporting only
  `{pullRequest}` and `{headSha}` substitutions. For `/previews/variants-7/review`,
  the produced `review/q.html` must be hosted at that directory's `q.html`.

The trusted component's supervised `resolve` call runs variables/custom checkers
only in the unprivileged job, under the approved Quarto author-code trust model.
It may create transient tested proposals, but never writes the source manifest.
The producer verifies the persisted lease is unchanged, rejects altered old
proposal/decision history, projects enriched component responses to the six
neutral record keys and requires explicit passing real-test reports. Execution,
grading/test and budget failures stop; nothing is resampled into success.

It emits one `variants-records.json` and canonical `review/<label>.html` pages.
Card URLs share safe stable `review.card_id` anchors with actual table rows.
Question reports contain no comment IDs: first-run comments do not yet exist.
Records are capped below the privileged 16 MiB archive bound; aggregate review
HTML is capped at 32 MiB. Output must be a fresh directory outside both checkouts.
The same-run `variants / check` job separately applies the required approval gate
to that exact neutral report. Thus a zero-approved question produces review
evidence while its publication check fails. Below-target warnings remain.

## Privileged preview/decision boundary

`variants-preview.yml` is a separate default-branch `workflow_run` template. Its
writer checks out only trusted default code, never the triggering PR source. It
does not extract HTML or execute artifact contents. `refresh_run` derives a PR
selector from bounded neutral JSON, then independently proves the requested run,
repository, PR/head, successful records job, trusted producer SHA and archive
digest before any comment effect. Exact-run selection cannot fall back to another
head's/latest report.

Owned comments are located by the hidden question marker and authenticated bot
login. First-run creation needs no preexisting comment ID. Updates reread the
latest own-comment body immediately before rendering/writing, so an intervening
tick is merged as exact passing consent. Duplicate owned question comments fail.
The recorder later fetches that real comment and matches its marker and checked
tokens against the exact artifact; it cannot accept an artifact-supplied comment
ID. Branch mutation remains atomic `expectedHeadOid`, followed by explicit
expected-head dispatch.

The trusted `.github/ctm-variants-producer.json` is an explicit list of the full
producer closure, never supplied by the PR artifact. Include the workflow,
entrypoint, `.github/ctm-variants.json`, dependency pins/requirements, canonical
installed native manifest and every native file it names, checker descriptor and
wheel, math wrapper/resolver and all imported helpers, installer/bootstrap/build
configuration and locks. The adapter compares each exact-head blob to the
API-observed protected-default blob before writing. Keep this inventory complete
when the installed closure changes; a partial hand-written example is not an
activation-ready inventory. The existing canonical native producer includes the
new module/launcher without changing browser wheels.

## Remaining actual acceptance

The source templates upload HTML and include an inactive Pages publishing step;
**no template was activated and no site was published here**. The sample
preview host must be replaced with the course's actual Pages origin. The inactive
trusted preview template now exports the authenticated exact-run HTML archive
and publishes only `previews/variants-<PR>/review/` using a commit-pinned Pages
action with `keep_files: true`. The preview workflow serializes its own Pages updates repository-wide. Before
activation, the main site publisher must use the same global concurrency group
and preserve `previews/`; this template cannot prevent a separate publisher
from racing or deleting preview subtrees. Native cards remain
resolved Markdown text, not a real component-rendered Try it view. No public URL
or live preview route was proven by these tests.

Retirement of sticky comments for deleted questions and the
large-project summary are unfinished. GitHub provides no atomic joint operation
for a human comment edit and a sticky update; current snapshots are reread, and
the preview workflow serializes its own refreshes repository-wide. Required-check attachment
must be observed on a real explicitly dispatched PR-head run: merely declaring
the template/job or creating a dispatch is not that proof. This remains HOLD.

Focused source checks: producer6, sticky fake-transport4, adapter8 and native
distribution3. These overlap earlier native checks and are not a new broad
acceptance campaign.

Handwritten `pool: true` questions without variables are also discovered. Their
trusted supervised `check-pool` action must pass teacher answers and authored
cases for every task. The producer emits a bounded separate `pool-checks.json`
receipt and the inactive template uploads it as `ctm-pool-checks`. Pools never
receive native proposal identities, manifests or approvals. Ordinary Quarto pool
rendering remains independent of this CI action.


The Pages exporter verifies exact current PR/run/producer, all neutral manifests,
archive API digest and bounded member inventory before writing files. Only the
expected per-question UTF-8 HTML pages are accepted; traversal, extra files,
symlinks, missing anchors and stale heads fail. It never executes downloaded HTML
or authored PR source. The publisher preserves the existing Pages branch and
fixed destination subtree. This is inactive source/fake-download proof only: no
Pages deployment or public URL was attempted, and actual required-check status
attachment remains unobserved. The checked-in templates remain outside
`.github/workflows`.

The inactive `variants.yml` dispatch form also accepts optional `generate_more`
with one discovered native variable-question label. Only an authenticated
exact-head dispatch can request it; unknown labels and handwritten pools fail.
The selected question uses supervised `resolve-more`, while other questions use
ordinary read-only resolution. Generated proposals remain in the artifact and
review until a human Copy file commit or an explicit bot decision records them;
this action never changes a source manifest. G1 review pages link to GitHub's
native Actions form and show/copy the exact branch, PR, head and label inputs.
They contain no browser generator, credentials or custom dispatch form. Source
and fake-resolution/UI checks do not prove a live dispatch or status attachment.

Resolved teacher-answer rendering is optional presentation metadata. A question
may carry `teacherDisplays` keyed by current candidate identity and exact teacher
field name; legacy artifacts omit it. The producer captures only component
response projections, and the privileged adapter validates every mapping and the
shared bounded MathML/LaTeX sanitizer before any write. Neutral six-field
candidates, authored options, hashes and history remain unchanged. The canonical
teacher input is always retained beside the display; an omitted or unsupported
component display uses that input, while malformed supplied artifact metadata is
rejected. No privileged authored-code execution is introduced.
