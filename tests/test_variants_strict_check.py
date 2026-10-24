"""Strict CI rejects stale approvals; ordinary publication retains valid ones."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authoring'))
from ctm_variants import history
from ctm_variants.model import candidate, snapshot, VariantError
from ctm_variants.producer import check


def record(locator, value):
    return candidate(locator, snapshot([str(value)], {'Answer': str(value)}, {}, {'x': str(value)}),
                     tests={'passed': True}, data={'options': {'variants': 1}})


def decided(records, statuses=None):
    value = history.append_proposals(history.empty('q'), [{'record': item, 'tape': []} for item in records])
    for item, status in zip(records, statuses or ['approved'] * len(records)):
        value = history.decision(value, records, item['id'], status)
    return value


def report(value, records):
    return {'questions': [{'label': 'q', 'manifest': value, 'records': records}]}


class StrictCheckTests(unittest.TestCase):
    def test_changed_or_gone_approval_fails_strict_ci_but_publish_keeps_current(self):
        current, old = record('current', 1), record('old', 2)
        value = decided([current, old])
        for records, state in [([current, record('old', 3)], 'changed'), ([current], 'gone')]:
            with self.subTest(state=state):
                selected = history.publication(value['decisions'], records, target=1)
                self.assertEqual(selected['ids'], ['current'])
                with self.assertRaisesRegex(VariantError, r'q:.*Variant 2 \(old\) is ' + state):
                    check(report(value, records))

    def test_unique_content_move_is_current_and_changed_rejections_do_not_block(self):
        old, rejected = record('old', 1), record('rejected', 2)
        value = decided([old, rejected], ['approved', 'rejected'])
        self.assertEqual(check(report(value, [record('renamed', 1), record('rejected', 3)])), [])
        self.assertEqual(check(report(value, [record('renamed', 1)])), [])

    def test_reapproval_clears_strict_failure_and_below_target_still_warns(self):
        current, old = record('current', 1), record('old', 2)
        value = decided([current, old])
        changed = record('old', 3)
        value = history.append_proposals(value, [{'record': changed, 'tape': []}])
        value = history.decision(value, [current, changed], 'old', 'approved')
        self.assertEqual(check(report(value, [current, changed])), [])
        current['data']['options']['variants'] = 3
        self.assertIn('target 3', check(report(value, [current, changed]))[0])


if __name__ == '__main__':
    unittest.main()
