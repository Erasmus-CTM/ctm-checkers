"""Semantic Python contracts for lossless browser manifests; no grading port."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "authoring"))
from ctm_variants import history
from ctm_variants.browser_manifest import SCRIPT
from ctm_variants.model import candidate, snapshot
from ctm_variants.review import apply_decisions


class BrowserManifestTests(unittest.TestCase):
    def export(self, value, records, selections, *, failed=False):
        runner = SCRIPT + "\nconst p=JSON.parse(require('fs').readFileSync(0,'utf8'));try{process.stdout.write(CTMManifestExport.apply(...p));}catch(e){console.error(e.message);process.exitCode=1;}"
        arguments = [json.dumps(value), json.dumps(records), selections]
        result = subprocess.run(["node", "-e", runner], input=json.dumps(arguments), text=True,
                                capture_output=True, timeout=10)
        if failed:
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        exported = history.validate(json.loads(result.stdout))
        expected = apply_decisions(value, records, selections)
        self.assertEqual(exported, expected)
        self.assertEqual(exported["proposals"], value["proposals"])
        self.assertEqual(exported["events"][:len(value["events"])], value["events"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "q.yml"
            lease = history.write(path, value, base_hash=None)
            history.write(path, exported, base_hash=lease)
            self.assertEqual(history.load(path, value["question"])[0], expected)
        return exported

    def item(self, locator, number, **options):
        return candidate(locator, snapshot([str(number)], {"Answer": str(number)}, {}, {"x": str(number)}),
                         note="Norsk æ — " + locator, tests={"passed": True}, **options)

    def retained(self, records):
        return history.append_proposals(history.empty("q"), [{"record": row, "tape": [2**80, -(2**90)]} for row in records])

    def select(self, record, status="approved", **metadata):
        return dict(id=record["id"], hash=record["hash"], status=status, **metadata)

    def test_large_numbers_unicode_metadata_and_multi_event_append(self):
        records = [self.item("a", 1, data={"huge": 2**100, "fraction": 1.2345678901234567}), self.item("b", 2)]
        value = self.retained(records)
        first = self.export(value, records, [self.select(records[0]), self.select(records[1], "rejected", reason="</script> æ")])
        self.assertEqual([row["n"] for row in first["decisions"]], [1, 2])
        # A repeated identical decision adds no event; by/date are informational.
        self.export(first, records, [self.select(records[0])])
        # Use a separate valid high-number chain instead of rewriting old events.
        high = history.empty("q")
        high["proposals"] = value["proposals"]
        high_entry = dict(first["decisions"][0], n=2**70)
        high["decisions"] = [high_entry]
        high["events"] = [{"before": [], "after": [high_entry]}]
        result = self.export(high, records, [self.select(records[1], by="informational", date="2026-10-23")])
        self.assertEqual(result["decisions"][-1]["n"], 2**70 + 1)

    def test_changed_moved_and_duplicate_content_preserve_native_numbers(self):
        old = self.item("old", 1)
        value = history.decision(self.retained([old]), [old], "old", "approved")
        moved = self.item("renamed", 1)
        value = history.append_proposals(value, [{"record": moved, "tape": []}])
        result = self.export(value, [moved], [self.select(moved)])
        self.assertEqual(result["decisions"][0]["n"], 1)
        changed = self.item("renamed", 3)
        result = history.append_proposals(result, [{"record": changed, "tape": []}])
        self.export(result, [changed], [self.select(changed)])
        tied = [self.item("A", 1), self.item("B", 1)]
        tied_value = self.retained(tied)
        tied_value = history.decision(tied_value, tied, "B", "approved")
        final = self.export(tied_value, tied, [self.select(tied[0]), self.select(tied[1], "rejected")])
        self.assertEqual([(row["id"], row["n"]) for row in final["decisions"]], [("B", 1), ("A", 2)])

    def test_stale_hash_failed_tests_duplicate_decisions_and_missing_tape_fail_closed(self):
        item = self.item("a", 1)
        value = self.retained([item])
        self.export(value, [item], [dict(self.select(item), hash="stale")], failed=True)
        self.export(value, [item], [self.select(item)] * 2, failed=True)
        failed = dict(item, tests={"passed": False})
        self.export(value, [failed], [self.select(failed)], failed=True)
        self.export(history.empty("q"), [item], [self.select(item)], failed=True)

    def test_transition_matrix_matches_native_with_migrations_ties_and_bulk_order(self):
        old = [self.item("A", 1), self.item("B", 2)]
        initial = self.retained(old)
        for row in old:
            initial = history.decision(initial, old, row["id"], "approved")
        for changed in range(4):
            for renamed in range(4):
                with self.subTest(changed=changed, renamed=renamed):
                    records = [self.item(("new-" if renamed & (1 << i) else "") + row["id"],
                                         3 if changed & (1 << i) else i + 1) for i, row in enumerate(old)]
                    records.append(self.item("C", 1))
                    value = initial
                    known = {(p["record"]["id"], p["record"]["hash"]) for p in value["proposals"]}
                    value = history.append_proposals(value, [{"record": row, "tape": []} for row in records
                        if (row["id"], row["hash"]) not in known])
                    order = records[::-1] if renamed % 2 else records
                    self.export(value, records, [self.select(row, "rejected" if i % 2 else "approved")
                                                 for i, row in enumerate(order)])

    def test_gone_approval_can_only_retire_with_retained_hash_and_reason(self):
        old, current = self.item("gone", 1), self.item("live", 2)
        value = self.retained([old, current])
        for row in (old, current):
            value = history.decision(value, [old, current], row["id"], "approved")
        retired = self.export(value, [current], [self.select(old, "rejected", reason="Removed from lesson")])
        self.assertEqual(retired["decisions"][0]["n"], 1)
        self.assertEqual(retired["decisions"][0]["snapshot"], value["decisions"][0]["snapshot"])
        for selection in (self.select(old), self.select(old, "rejected"), dict(self.select(old, "rejected", reason="gone"), hash="stale")):
            self.export(value, [current], [selection], failed=True)
        moved = self.item("renamed", 1)
        self.export(value, [current, moved], [self.select(old, "rejected", reason="not actually gone")], failed=True)


if __name__ == "__main__":
    unittest.main()
