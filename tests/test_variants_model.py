"""Native variant identity contracts. AGPL-3.0-or-later."""
import copy
import itertools
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "authoring"))
from ctm_variants.model import (VariantError, candidate, classify, content_hash,
                                decide, snapshot, validate_entries, validate_snapshot)


def sample(locator="a=2", maths=None, variables=None, grading=None, teacher=None):
    return candidate(locator, snapshot(
        maths if maths is not None else ["2", "3"],
        teacher if teacher is not None else {"answer": "2/3"},
        grading if grading is not None else {"mode": "equivalent"},
        variables if variables is not None else {"a": "2"}))


def approved(item, number=1, status="approved"):
    entry = decide([], [item], item["id"], status)[0]
    entry["n"] = number
    return entry


class SnapshotTests(unittest.TestCase):
    def test_ordered_maths_and_teacher_keys_are_semantic(self):
        baseline = sample()
        for changed in (sample(maths=["3", "2"]), sample(teacher={"answer": "3/2"}),
                        sample(grading={"mode": "numeric"}),
                        sample(grading={"mode": "equivalent", "tolerance": "0.1"})):
            self.assertNotEqual(baseline["hash"], changed["hash"])
        first = sample(teacher={"numerator": "2", "denominator": "3"})
        swapped = sample(teacher={"denominator": "3", "numerator": "2"})
        self.assertNotEqual(first["hash"], swapped["hash"])

    def test_variable_names_and_unused_helpers_do_not_change_content(self):
        first = sample(variables={"a": "2", "unused": "7"})
        renamed = sample("b=2", variables={"b": "2", "unused": "99"})
        self.assertEqual(first["hash"], renamed["hash"])
        self.assertNotEqual(first["snapshot"]["checksum"], renamed["snapshot"]["checksum"])

    def test_resolved_values_in_prose_are_in_the_ordered_math_stream(self):
        self.assertNotEqual(sample(maths=["7", "2", "3"])["hash"],
                            sample(maths=["8", "2", "3"])["hash"])

    def test_old_snapshot_verifies_independently_but_rejects_hand_edits(self):
        old = sample()["snapshot"]
        self.assertIs(validate_snapshot(old), old)
        for mutate in (
            lambda value: value["math"].reverse(),
            lambda value: value["teacher"][0].__setitem__(1, "9"),
            lambda value: value["grading"].__setitem__("mode", "string"),
            lambda value: value["variables"].__setitem__("a", "9"),
        ):
            changed = copy.deepcopy(old)
            mutate(changed)
            with self.assertRaisesRegex(VariantError, "checksum"):
                validate_snapshot(changed)
        self.assertNotEqual(sample(maths=["changed"])["hash"], content_hash(old))
        validate_snapshot(old)

    def test_schema_and_non_json_values_fail_closed(self):
        for args in (([], {}, {}, []), ([], {}, [], {}), ("x", {}, {}, {})):
            with self.assertRaises(VariantError):
                snapshot(*args)
        with self.assertRaises(VariantError):
            sample(grading={"tolerance": float("nan")})
        with self.assertRaises(VariantError):
            sample(grading={1: "value"})
        with self.assertRaises(VariantError):
            candidate("a", sample()["snapshot"], data=[])
        with self.assertRaises(VariantError):
            candidate("", sample()["snapshot"])

    def test_snapshots_and_decisions_do_not_alias_caller_data(self):
        item = sample()
        entries = decide([], [item], item["id"], "approved")
        item["snapshot"]["math"][0] = "mutated"
        self.assertEqual(entries[0]["snapshot"]["math"], ["2", "3"])
        validate_entries(entries)


class IdentityTests(unittest.TestCase):
    def test_changed_moved_current_gone_and_new(self):
        one, two, three = sample("one"), sample("two", ["5"]), sample("three", ["7"])
        entries = [approved(one, 1), approved(two, 5), approved(three, 9)]
        candidates = [sample("one", ["changed"]), sample("renamed-two", ["5"]), sample("new", ["11"])]
        rows = classify(entries, candidates)
        self.assertEqual([row["state"] for row in rows["entries"]], ["changed", "moved", "gone"])
        self.assertEqual([item["id"] for item in rows["new"]], ["new"])
        self.assertEqual(classify(entries, [one, two, three])["entries"][0]["state"], "current")

    def test_exact_matches_reserved_before_hash_moves(self):
        a, b = sample("a", ["1"]), sample("b", ["2"])
        candidates = [sample("a", ["2"]), sample("b", ["2"])]
        for entries in ([approved(a, 1), approved(b, 2)], [approved(b, 2), approved(a, 1)]):
            states = {row["entry"]["id"]: row["state"] for row in classify(entries, candidates)["entries"]}
            self.assertEqual(states, {"a": "changed", "b": "current"})

    def test_math_existing_locator_is_changed_but_content_first_can_move(self):
        entry = approved(sample("a", ["1"]), 7)
        candidates = [sample("a", ["2"]), sample("b", ["1"])]
        math = classify([entry], candidates)
        content_first = classify([entry], candidates, hash_first=True)
        self.assertEqual(math["entries"][0]["state"], "changed")
        self.assertEqual(math["entries"][0]["candidate"]["id"], "a")
        self.assertEqual(content_first["entries"][0]["state"], "moved")
        self.assertEqual(content_first["entries"][0]["candidate"]["id"], "b")

    def test_content_first_collision_retains_historical_locator_and_consumes_once(self):
        # Classification is not a STACK decision writer: historical and resolved
        # locators stay separate when content swaps between existing locators.
        entries = [approved(sample("a", ["1"]), 3), approved(sample("b", ["2"]), 9)]
        candidates = [sample("a", ["2"]), sample("b", ["1"])]
        for old_order in itertools.permutations(entries):
            for new_order in itertools.permutations(candidates):
                result = classify(list(old_order), list(new_order), hash_first=True)
                rows = {row["entry"]["n"]: row for row in result["entries"]}
                self.assertEqual(rows[3]["entry"]["id"], "a")
                self.assertEqual(rows[3]["candidate"]["id"], "b")
                self.assertEqual(rows[9]["entry"]["id"], "b")
                self.assertEqual(rows[9]["candidate"]["id"], "a")
                self.assertEqual([row["state"] for row in result["entries"]], ["moved", "moved"])
                self.assertEqual(result["new"], [])
        self.assertEqual([entry["id"] for entry in entries], ["a", "b"])

    def test_duplicate_new_hashes_never_carry_a_decision(self):
        entry = approved(sample("old"), 4)
        candidates = [sample("new-a"), sample("new-b")]
        for order in itertools.permutations(candidates):
            result = classify([entry], list(order))
            self.assertEqual(result["entries"][0]["state"], "gone")
            self.assertEqual(len(result["new"]), 2)
            updated = decide([entry], list(order), "new-a", "approved")
            self.assertEqual([row["n"] for row in updated], [4, 5])

    def test_duplicate_old_hashes_never_choose_first_decision(self):
        entries = [approved(sample("old-a"), 2), approved(sample("old-b"), 8)]
        for order in itertools.permutations(entries):
            result = classify(list(order), [sample("new")])
            self.assertEqual([row["state"] for row in result["entries"]], ["gone", "gone"])
            updated = decide(list(order), [sample("new")], "new", "approved")
            self.assertEqual(updated[-1]["n"], 9)

    def test_numbers_survive_moves_changes_rejections_and_gone_records(self):
        entries = [approved(sample("old"), 6), approved(sample("gone", ["99"]), 20, "rejected")]
        moved = sample("renamed")
        entries = decide(entries, [moved], moved["id"], "rejected", reason="review")
        self.assertEqual([(row["n"], row["id"]) for row in entries], [(6, "renamed"), (20, "gone")])
        changed = sample("renamed", ["new content"])
        entries = decide(entries, [changed], changed["id"], "approved")
        self.assertEqual(entries[0]["n"], 6)
        entries = decide(entries, [changed, sample("fresh", ["fresh"])], "fresh", "approved")
        self.assertEqual(entries[-1]["n"], 21)

    def test_duplicate_ids_numbers_and_corrupted_hashes_fail(self):
        item = sample()
        entry = approved(item)
        for entries in ([entry, copy.deepcopy(entry)], [dict(entry, n=True)],
                        [dict(entry, hash="0" * 16)], [dict(entry, extra="unknown")]):
            with self.assertRaises(VariantError):
                validate_entries(entries)
        with self.assertRaises(VariantError):
            classify([], [item, item])
        with self.assertRaises(VariantError):
            decide([], [item], "absent", "approved")


if __name__ == "__main__":
    unittest.main()
