# Trusted-base GitHub adapter checkpoint

This is an **inactive template and fake-transport-tested adapter**, not an
installed bot. No live comments, decision commits or workflow dispatches were
sent to test it. Trusted records/sticky workflow glue now exists as source and
inactive templates, tested using fake resolvers and transports. Day-one bot
completion still needs course configuration/installation and an actual observed
run, preview hosting, rejection commands, and observation that the explicitly
dispatched check attaches to its new commit.

The privileged native launcher is `ctm-variants-bot.py`, included by the canonical
native-only producer. It runs from a trusted default-branch checkout with isolated
Python imports. It never checks out, imports or executes PR course code. Its REST
transport bounds response/archive sizes and strips the bearer token on approved
HTTPS artifact redirects. Tokens are not printed.

Before recording, it obtains the event sender's repository write permission,
fetches the current own-bot comment, checks that it belongs to the PR, and rejects
forks, closed PRs and default-branch writes. It fetches the current branch head
from GitHub instead of trusting event or artifact claims. The mandatory trusted
producer inventory is read from the default checkout, never from artifact data.
Every listed producer blob must match between the exact PR head and the observed
trusted default-branch SHA, and that comparison is repeated before recording.

The reviewed inventory must enumerate the complete producer closure: workflow,
records entrypoint, native manifests, installers/bootstrap, scripts and imported
helpers, build configuration, locks and pins. The future unprivileged records
workflow must execute its producer from an exact trusted base SHA, not a PR's
replacement pipeline; it reads authored source from the PR. Variables and custom
checkers retain the approved Quarto author-code trust model and run unprivileged.
This work introduces no new OS sandbox policy.

The adapter accepts a completed exact-head `pull_request` run of
`.github/workflows/variants.yml` with matching repository/PR, or its explicit
`workflow_dispatch` successor with matching repository, head repository and PR
branch. Dispatch runs need not have a GitHub `pull_requests` link. Both require a successful
`variants-records` job. The overall run may fail the zero-approved publication
gate. It requires one nonexpired `ctm-variants-records` artifact, verifies the
GitHub archive SHA256 digest and reads one bounded `variants-records.json` member
without extracting paths. Its envelope is:

```json
{"version":1,"headSha":"<PR head>","producerSha":"<trusted producer SHA>","event":"pull_request or workflow_dispatch","expectedHead":"<PR head>","runId":123,"repositoryId":456,"pullRequest":7,"questions":[{"label":"q","path":"_variants/q.yml","baseHash":"<current manifest digest or null>","manifest":{},"records":[],"cards":{}}]}
```

Only canonical `_variants/<label>.yml` paths are writable. The native format is
UTF-8 JSON, a YAML subset; general YAML is not interpreted by this adapter.
Artifact histories may append proposals but cannot alter the exact-head manifest's
old proposals, decisions or events. Current id/hash/number tokens and explicitly
passing tests are validated before the shared pure decision API is called.
Comment IDs are deliberately absent from producer artifacts: the first artifact
exists before its comment. The privileged recorder fetches the actual own-bot
comment, matches its exact hidden question marker to one artifact question and
validates all checked identity tokens. Preview refresh similarly looks up own
comments dynamically; duplicate owned question comments fail instead of choosing
one. Canonical card URLs must end in the shared native review anchor.

The only branch mutation is GraphQL `createCommitOnBranch` with
`expectedHeadOid`; a concurrent branch move fails atomically. PR/producer heads
are rechecked beforehand, and the resulting head is checked again before the
explicit `variants.yml` dispatch, whose inputs include `expected_head` and the PR
number. The receiving workflow must declare these inputs and fail if its observed
head differs. Dispatch creation alone is not proof of check-status attachment.
The receiving trusted records producer must verify dispatch inputs against the
actual PR/head before succeeding, and bind the event and expected head into its
artifact. This permits repeated approvals after bot-token commits that do not
trigger an ordinary pull-request run; wrong-branch/event/head artifacts fail.
The current comment identity, body and update timestamp are reread immediately
before the CAS; changed intent fails without recording. GitHub provides no joint
atomic operation for a comment edit and branch commit, so a later comment edit
cannot retroactively cancel a successful recording.

`templates/variants-decide.yml`, `variants.yml` and `variants-preview.yml` are
kept outside `.github/workflows`; they do not activate automation. The records
workflow runs only trusted native tooling against a separate authored checkout
with read permissions. A separate default-branch `workflow_run` job reads neutral
JSON and can write sticky comments; it never executes the triggering course or
extracts its HTML. The decide workflow retains per-PR serialization, pinned
actions and event-file parsing. Install only after configuring/reviewing the
complete producer inventory and actual preview destination. See
[producer/workflow installation boundaries](variants-producer.md).

Focused tests: `python -m unittest discover -s tests -p
test_variants_github_bot.py`; planner tests remain in `test_variants_bot.py`.
The fake transport covers own-comment/write-permission/no-fork checks, producer
and run substitution, artifact digest/provenance/path/manifest faults, archive
path rejection, before-write head changes, a race inside the atomic CAS, and the
exact downstream dispatch. No API request in these tests leaves the process.
