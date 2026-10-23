"""Review persistence contracts; no browser runtime is involved."""
import copy
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "authoring"))
from ctm_variants import history
from ctm_variants.model import VariantError, candidate, snapshot


def record(locator="a", value="2"):
    return candidate(locator, snapshot([value], {"answer": value}, {"mode": "equivalent"}), note=value)


def proposed(*records):
    return history.append_proposals(history.empty("q"), [{"record": item, "tape": []} for item in records])


class HistoryTests(unittest.TestCase):
    def test_proposals_allocate_no_numbers_and_preserve_versions(self):
        original = history.empty("q")
        first = {"record": record(), "tape": [0]}
        saved = history.append_proposals(original, [first])
        changed = {"record": record(value="3"), "tape": [0]}
        expanded = history.append_proposals(saved, [first, changed])
        self.assertEqual(expanded["proposals"], [first, changed])
        self.assertEqual(expanded["decisions"], [])
        self.assertEqual(original, history.empty("q"))
        tampered = copy.deepcopy(first)
        tampered["tape"] = [1]
        with self.assertRaisesRegex(VariantError, "modified"):
            history.append_proposals(saved, [tampered])

    def test_explicit_decisions_keep_number_and_complete_old_snapshots(self):
        first, second = record(), record("b", "3")
        value = history.decision(proposed(first, second), [first, second], "a", "approved")
        value = history.decision(value, [first, second], "b", "rejected", reason="not useful")
        changed = record(value="4")
        value = history.append_proposals(value, [{"record": changed, "tape": []}])
        value = history.decision(value, [changed, second], "a", "approved")
        self.assertEqual([r["n"] for r in value["decisions"]], [1, 2])
        self.assertEqual(value["events"][0]["after"][0]["snapshot"], first["snapshot"])
        broken = copy.deepcopy(value)
        broken["events"][1]["before"] = []
        with self.assertRaisesRegex(VariantError, "chain"):
            history.validate(broken)

    def test_stale_write_missing_file_lease_and_lock_are_safe(self):
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "variants.yml"
            value, token = history.load(path, "q")
            self.assertIsNone(token)
            token = history.write(path, value, base_hash=None)
            decided = history.decision(history.append_proposals(value, [{"record": record(), "tape": []}]),
                                       [record()], "a", "approved")
            with self.assertRaisesRegex(VariantError, "changed"):
                history.write(path, decided, base_hash=None)
            self.assertEqual(history.load(path, "q"), (value, token))
            lock = path.with_name(path.name + ".lock")
            lock.write_text("held", encoding="utf-8")
            with self.assertRaisesRegex(VariantError, "locked"):
                history.write(path, decided, base_hash=token)
            lock.unlink()
            next_token = history.write(path, decided, base_hash=token)
            self.assertNotEqual(token, next_token)
            with self.assertRaisesRegex(VariantError, "cannot be rewritten"):
                history.write(path, history.empty("q"), base_hash=next_token)
            self.assertEqual(history.load(path, "q"), (decided, next_token))
            self.assertNotIn(b"\r\n", path.read_bytes())
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_publish_required_optional_and_changed_rejection(self):
        a, b = record(), record("b", "3")
        with self.assertRaisesRegex(VariantError, "at least one"):
            history.publication([], [a, b])
        self.assertEqual(history.publication([], [a, b], render_mode="review")["ids"], ["a", "b"])
        value = history.decision(proposed(a, b), [a, b], "a", "approved")
        decisions = history.decision(value, [a, b], "b", "rejected")["decisions"]
        self.assertEqual(history.publication(decisions, [a, b])["ids"], ["a"])
        self.assertEqual(history.publication(decisions, [a, record("b", "4")], approval="optional")["ids"], ["a"])
        with self.assertRaisesRegex(VariantError, "at least one"):
            history.publication(decisions, [record(value="4"), b])


if __name__ == "__main__":
    unittest.main()
