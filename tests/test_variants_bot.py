import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authoring'))
from ctm_variants.bot import plan, token, bulk_token
from ctm_variants.model import VariantError

class BotTests(unittest.TestCase):
    def setUp(self):
        self.row = {'id': 'value:$(do-not-execute)', 'hash': 'a' * 16, 'tests': {'passed': True}}
        self.args = dict(label='q', records=[self.row], decisions=[], sender='teacher', permission='write',
                         comment_author='ctm[bot]', bot_login='ctm[bot]', head_repository_id=1, base_repository_id=1)
        self.body = '- [x] maths ' + token('q', self.row['id'], self.row['hash'])

    def test_explicit_tick_and_idempotence(self):
        selected = plan(self.body, **self.args)["decisions"]
        self.assertEqual(selected, [dict(id=self.row['id'], hash='a'*16, status='approved', by='teacher')])
        self.assertEqual(plan(self.body+'\n'+self.body, **self.args)['decisions'], selected)
        self.args['decisions'] = [dict(selected[0], n=4)]
        self.assertEqual(plan(self.body, **self.args)['decisions'], [])
        self.body = '- [x] ' + token('q', self.row['id'], self.row['hash'], 4)
        self.assertEqual(plan(self.body, **self.args)["decisions"], [])
        self.assertEqual(plan(self.body.replace('[x]', '[ ]'), **self.args)['decisions'], [])

    def test_bulk_retains_named_failing_exclusions(self):
        failed = dict(self.row, id='failed', tests={'passed': False})
        self.args['records'].append(failed)
        body = '- [x] Approve all passing ' + bulk_token('q', self.args['records'], [])
        result = plan(body, **self.args)
        self.assertEqual([row['id'] for row in result['decisions']], [self.row['id']])
        self.assertEqual(result['notPassing'], ['failed'])
        self.args['records'][0] = dict(self.row, hash='b'*16)
        with self.assertRaises(VariantError):
            plan(body, **self.args)

    def test_malformed_and_conflicting_identities_fail_closed(self):
        bodies = ['- [x] <!-- ctm-variant:a -->',
                  '- [x] <!-- ctm-variant:' + 'a'*262145 + ' -->',
                  self.body+'\n- [x] '+token('q', self.row['id'], 'b'*16),
                  '- [x] '+bulk_token('other', [self.row], [])]
        for body in bodies:
            with self.subTest(length=len(body)), self.assertRaises(VariantError):
                plan(body, **self.args)
        for key, value in [('permission', None), ('sender', ''), ('bot_login', '')]:
            with self.subTest(key=key), self.assertRaises(VariantError):
                plan(self.body, **dict(self.args, **{key:value}))
        with self.assertRaises(VariantError):
            plan(self.body, **dict(self.args, records=[self.row, self.row]))

    def test_forged_stale_and_failed_ticks_fail_closed(self):
        for key, value in [('permission', 'read'), ('comment_author', 'attacker'), ('head_repository_id', 2)]:
            with self.subTest(key=key), self.assertRaises(VariantError):
                plan(self.body, **dict(self.args, **{key: value}))
        for body in [self.body.replace('ctm-variant:', 'other:'), 
                     '- [x] '+token('other', self.row['id'], 'a'*16),
                     '- [x] '+token('q', self.row['id'], 'b'*16),
                     '- [x] '+token('q', self.row['id'], 'a'*16, 1)]:
            with self.subTest(body=body), self.assertRaises(VariantError):
                plan(body, **self.args)
        self.row['tests'] = {}
        with self.assertRaises(VariantError):
            plan(self.body, **self.args)

if __name__ == '__main__':
    unittest.main()
