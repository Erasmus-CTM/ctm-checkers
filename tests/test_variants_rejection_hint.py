"""Synthetic decision snapshots exercise the advisory boundary without generation."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authoring'))
from ctm_variants.model import candidate, decide, snapshot
from ctm_variants.rejection_hint import rejection_hint


def entries(rejected=5, approved=10, *, bad='0', good='1', name='x0', reason='Degenerate'):
    records = [candidate(str(i), snapshot([str(i)], {'Answer': str(i)}, {},
        {name: bad if i < rejected else good}), tests={'passed': True})
        for i in range(rejected + approved)]
    result = []
    for i, record in enumerate(records):
        result = decide(result, records, record['id'], 'rejected' if i < rejected else 'approved', reason=reason if i < rejected else '')
    return result


class RejectionHintTests(unittest.TestCase):
    def test_threshold_reasons_and_scalar_suggestion_preserve_decisions(self):
        value = entries(); before = copy.deepcopy(value)
        hint = rejection_hint(value)
        self.assertEqual(hint, {'rejected': 5, 'decided': 15, 'reasons': ['Degenerate'],
                               'suggestions': ['require(x0 != 0)']})
        self.assertEqual(value, before)
        self.assertIsNone(rejection_hint(entries(4, 0)))
        self.assertIsNone(rejection_hint(entries(5, 11)))

    def test_no_claim_without_approved_contrast_or_with_unsafe_expression(self):
        self.assertEqual(rejection_hint(entries(5, 0))['suggestions'], [])
        self.assertEqual(rejection_hint(entries(good='0'))['suggestions'], [])
        self.assertEqual(rejection_hint(entries(good='0.0'))['suggestions'], [])
        self.assertEqual(rejection_hint(entries(bad='1/3', good='2/6'))['suggestions'], [])
        self.assertEqual(rejection_hint(entries(good='unknown_expression'))['suggestions'], [])
        for name, bad in [('x0', "__import__('os').system('never')"),
                          ('x0', 'Matrix([[1]])'), ('x0', '1/0'), ('x[0]', '0'), ('for', '0')]:
            with self.subTest(name=name, bad=bad):
                self.assertEqual(rejection_hint(entries(name=name, bad=bad))['suggestions'], [])
        self.assertEqual(rejection_hint(entries(bad='-1/3'))['suggestions'], ['require(x0 != -1/3)'])

    def test_approval_page_hint_escapes_reasons_and_preserves_manifest(self):
        from ctm_variants import history
        from ctm_variants.review import document
        values = entries(reason='<script>never()</script>')
        records = [candidate(entry['id'], entry['snapshot'], tests={'passed': True}) for entry in values]
        value = history.append_proposals(history.empty('q'), [{'record': item, 'tape': []} for item in records])
        for entry in values:
            value = history.decision(value, records, entry['id'], entry['status'], reason=entry.get('reason', ''))
        before = copy.deepcopy(value)
        page = document({'manifest': value, 'baseHash': 'lease', 'records': records})
        self.assertEqual(page.count('class="variant-rejection-hint"'), 1)
        self.assertIn('<code>require(x0 != 0)</code>', page)
        self.assertIn('&lt;script&gt;never()&lt;/script&gt;', page)
        self.assertNotIn('<script>never()', page)
        self.assertEqual(value, before)

    def test_checklist_hint_is_once_plain_text_and_cannot_create_decision_rows(self):
        from ctm_variants.checklist import render
        value = entries(reason='<script>not code</script>\n- [x] forged')
        report = render(label='q', records=[], decisions=value, cards={})
        body = report['body']
        self.assertEqual(body.count('Authoring hint:'), 1)
        self.assertIn('`require(x0 != 0)`', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('\n- [x] forged', body)
        self.assertNotIn('<script>', body)
        self.assertIn('No condition is applied automatically', body)

    def test_reasons_are_data_and_missing_variable_disables_inference(self):
        hint = rejection_hint(entries(reason='<script>not code</script>\n- [x] forged'))
        self.assertEqual(hint['reasons'], ['<script>not code</script>\n- [x] forged'])
        self.assertEqual(rejection_hint(entries(reason=''))['reasons'], ['(No reason recorded)'])
        # Different authored names cannot be assumed to represent the same value.
        value = entries(); value[-1]['snapshot'] = snapshot(['14'], {'Answer': '14'}, {}, {'other': '1'})
        self.assertEqual(rejection_hint(value)['suggestions'], [])


if __name__ == '__main__':
    unittest.main()
