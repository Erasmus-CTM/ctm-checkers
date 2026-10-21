"""Coverage and mutation controls for native evidence collection (no CAS needed)."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('observe_changed', ROOT / 'tools/stack_native/observe_changed.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


class NativeEvidenceTests(unittest.TestCase):
    def test_revision_inventory_includes_removed_and_untagged_added_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

            git('init')
            table = root / 'tests/golden/stack/sample.jsonl'
            table.parent.mkdir(parents=True)
            row = lambda key, score: {'id': key, 'call': 'stack.answer_test', 'input': {}, 'output': {'correct': score}}

            def commit(values):
                table.write_text(''.join(json.dumps(value) + '\n' for value in values), encoding='utf-8')
                git('add', '.')
                git('-c', 'user.name=Evidence fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
                return git('rev-parse', 'HEAD')

            base = commit([row('unchanged', True), row('changed', False), row('removed', False)])
            head = commit([row('unchanged', True), row('changed', True), row('added', True)])
            actual = oracle.inventory(base, head, root=root)
            self.assertEqual({item['id']: item['revision'] for item in actual},
                             {'added': 'added', 'changed': 'changed', 'removed': 'removed'})

    def answer_pair(self):
        entry = {'after': {'call': 'stack.answer', 'output': {
            'validate': {'inputs': {'ans1': {'valid': True, 'feedback': ''}}},
            'grade': {'status': 'graded', 'score': 0.7, 'prts': {
                'prt1': {'score': 0.7, 'notes': ['prt1-1-F'], 'feedback': 'Try again.'}}}}}}
        result = [{'observation': {'inputs': {'ans1': {'status': 'score', 'errors': ''}},
                                  'prts': {'prt1': {'score': 0.7, 'branch_notes': ['prt1-1-F'],
                                                   'feedback': '<p>Try again.</p>', 'errors': ''}},
                                  'score': 0.7, 'runtimeerrors': []}}]
        return entry, result

    def test_semantic_comparison_and_score_branch_validation_message_mutations(self):
        entry, result = self.answer_pair()
        self.assertEqual(oracle.differences(entry, result), [])
        mutations = [
            lambda value: value['observation'].update(score=1),
            lambda value: value['observation']['prts']['prt1'].update(score=1),
            lambda value: value['observation']['prts']['prt1'].update(branch_notes=['prt1-1-T']),
            lambda value: value['observation']['prts']['prt1'].update(feedback='An unrelated change.'),
            lambda value: value['observation']['inputs']['ans1'].update(status='invalid'),
            lambda value: value['observation']['inputs']['ans1'].update(errors='Wrong input type.'),
            lambda value: value['observation']['prts']['prt1'].update(errors='CAS error'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                changed = copy.deepcopy(result)
                mutate(changed[0])
                self.assertTrue(oracle.differences(entry, changed))

    def test_native_null_verdict_never_counts_as_false_agreement(self):
        entry = {'after': {'call': 'stack.answer_test', 'output': {
            'correct': False, 'cas_valid': False, 'feedback': '', 'note': ''}}}
        result = [{'observation': {'verdict': None, 'valid': False, 'feedback': '', 'note': '', 'errors': ''}}]
        self.assertEqual(oracle.differences(entry, result)[0]['field'], 'correct')

    def test_second_imported_question_exception_is_visible(self):
        entry = {'after': {'call': 'stack.import', 'output': []}}
        self.assertEqual(oracle.differences(entry, [{'observation': {}}, {'exception': 'stack_exception: invalid'}])[0]['field'],
                         'native exception')

    def test_removed_rows_and_native_representations_remain_for_review(self):
        self.assertTrue(oracle.differences({'after': None}, [{'observation': {}}]))
        self.assertTrue(oracle.differences({'after': {'call': 'stack.import', 'output': []}}, [{'observation': {}}]))

    def test_question_test_disagreement_and_missing_case_are_visible(self):
        entry = {'after': {'call': 'stack.tests', 'output': {'results': [{'testcase': '1', 'passed': True}]}}}
        failed = [{'observation': {'tests': [{'testcase': '1', 'result': {'passed': False}}]}}]
        missing = [{'observation': {'tests': []}}]
        self.assertTrue(oracle.differences(entry, failed))
        self.assertTrue(oracle.differences(entry, missing))


if __name__ == '__main__':
    unittest.main()
