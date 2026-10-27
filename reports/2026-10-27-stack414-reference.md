# STACK 4.14 reference migration for M4a/M4b

The native runtime-v3 library is STACK `33383047af39c204bf4442802a058f8b918b2b1b`
(4.14.0). The Python input data, fixture importer and desktop oracle previously
used `10d323311b7f39fb7b092dd10ce75f7d8632f525` (4.13.1). This change aligns
those active references before introducing one shared JavaScript admission.
Runtime-v3 and its release/archive format are unchanged.

The source audit compares Git blobs at both exact upstream commits and the
checker baseline `aae41a65ad29cf7db50e3381a6b3a8e962da2fa6`.

| Source | SHA-256 at both pins |
|---|---|
| `stack/cas/security-map.json` | `6a0435870103287eb3ed2f4048e58f76be0e9abc81c0bde9afe76292978bfd58` |
| `stack/maximaparser/unicode/symbols-stack.json` | `dcdf658aa7d23d0767eeafa4249e166469d5ab2e37cbe8010a279b870aa5ea43` |
| `stack/maximaparser/unicode/letters-stack.json` | `38983ed0f7b43213fe59f09497601629007b4b6434b24f0b047b06bda2d044b7` |
| `tests/fixtures/answertestfixtures.class.php` | `db3eac5a85ec2d479b4b78a391995de32b8f956af99fa118791f5c81236b978f` |

All 2,303 imported fixture rows, IDs, notes, desired outcomes and source lines
are identical. All 35 corpus files are exact exports from the new commit.
After excluding only `metadata` and `prescribedmetadata`, their XML structure
is identical, including expressions, PRTs, question tests and deployed seeds.
Their actual imported models (including the same unsupported diagnostics) are
also identical. The four teaching copies receive the same upstream metadata;
the existing teaching corrections and strict presentation-only test remain.

The corpus replay still has 23 passing questions, one question with its two
known failures, three unsupported imports and eight unsupported instantiations.
The 162 replay cases, failed checks and complete per-question results are
unchanged. Only the recorded engine/source fingerprint and environment change.

All **6,193 existing STACK golden rows reproduce exactly from both source and
the actual built wheels**. No golden files or expected verdicts were changed.
Historical policy/evidence links retain their original old-pin provenance.

The upstream native library itself is not byte-identical: 17 Maxima source/test
files changed, recorded by the audit. Examples include assessment.mac, which
removes right-associative declarations for nounand/nounor; stackmaxima.mac
adds display support for unevaluated matrix calls and updates the library
version to 2026101500. The existing native PHP/Maxima and Pyodide/reference
suite is rerun with the new pin through the ctm-stack consumer. No policy
waiver is added for those changes. New native-image fingerprints invalidate
old cached images automatically.

Prepared backend metadata and source-bound variant fingerprints report the new
STACK pin. Existing required approvals are not copied to changed candidate
hashes; the ordinary review path remains in force.

Reproduce the structural audit with:

```sh
python tools/stack_native/check_reference_migration.py --stack-source /path/to/stack --out test-results/compliance/reference-migration.json
python tools/golden.py verify --adapter src --suite '^stack/'
python tools/golden.py verify --adapter wheel --suite '^stack/'
```

The STACK checkout must contain both source commits, and this repository must
contain the recorded checker baseline. The native workflow fetches both exact
old objects explicitly. The audit establishes provenance and structural
identity; fresh native execution is a separate gate.

This is a dependency of M4a/M4b. Shared input admission, the native compiler,
public card adapter and native variant producer remain subsequent work.
