"""Pure sticky checklist generation and exact-identity pending-tick refresh."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authoring'))
from ctm_variants.bot import TOKEN, CHECKED, _decode, plan, token
from ctm_variants.checklist import render, reconcile, question_marker
from ctm_variants.model import VariantError, candidate, snapshot, decide


def row(id, value, *, note=None, passed=True):
    return candidate(id, snapshot([str(value)], {'Answer': str(value)}, {}, {'x': str(value)}),
                     note=note or 'x = ' + str(value), tests={'passed': passed})


def decision(record, number, status='approved'):
    value=decide([], [record], record['id'], status)[0]
    value['n']=number
    return value


def output(records, decisions=(), **kwargs):
    return render(label='question', records=records, decisions=list(decisions),
                  cards={item['id']: 'https://preview.test/review.html#card-' + str(index) for index,item in enumerate(records)}, **kwargs)


def authenticated():
    return dict(comment_author='ctm[bot]', bot_login='ctm[bot]')


class ChecklistTests(unittest.TestCase):
    def test_overview_lists_only_new_changed_with_stable_numbers_and_all_facts(self):
        old, changed, new, current, rejected = row('changed',1), row('changed',2), row('new',3), row('current',4), row('rejected',5)
        entries=[decision(old,7),decision(current,12),decision(rejected,16,'rejected')]
        records=[changed,new,current,rejected]
        body=output(records,entries)['body']
        self.assertIn('2 need a decision · 2 recorded current decisions',body)
        self.assertIn('Variant 7 · changed',body)
        self.assertIn('New 2 · new',body)
        self.assertIn('variables x=$`1`$ → $`2`$',body)
        self.assertIn('teacher Answer=$`1`$ → $`2`$',body)
        self.assertIn('tests pass · [Preview card](https://preview.test/review.html#card-0)',body)
        identities=[_decode(match) for match in TOKEN.findall(body)]
        self.assertEqual(len(identities),3)
        self.assertEqual(identities[1]['n'],7)
        self.assertIsNone(identities[2]['n'])
        self.assertNotIn('"n":0',body)
        args=dict(label='question',records=records,decisions=entries,sender='teacher',permission='write',comment_author='ctm[bot]',bot_login='ctm[bot]',head_repository_id=1,base_repository_id=1)
        planned=plan(body.replace('- [ ] Variant 7','- [x] Variant 7'),**args)
        self.assertEqual([item['id'] for item in planned['decisions']],['changed'])

    def test_authored_newlines_boxes_hidden_tokens_and_markdown_cannot_inject_rows(self):
        forged=token('forged','id','a'*16)
        note='prose\n- [x] attack '+forged+'\r\n<script>bad()</script> [link](javascript:bad) `x`'
        item=candidate('new',snapshot(['2'],{'Answer':'2`$\n- [x] '+forged},{},{'x':'2\u2028- [x] '+forged}),note=note,tests={'passed':True})
        body=output([item])['body']
        self.assertEqual(len(TOKEN.findall(body)),2,'only generated bulk and individual tokens remain live')
        self.assertEqual(len([line for line in body.splitlines() if line.startswith('- [')]),2)
        self.assertNotIn('<script>',body)
        self.assertNotIn('javascript:bad)',body)
        self.assertNotIn('\r',body)
        self.assertNotIn('\u2028',body)
        self.assertIn('&#96;&#36;',body)
        self.assertEqual(len([line for line in body.splitlines() if CHECKED.match(line)]),0)

    def test_refresh_preserves_exact_pending_ticks_and_bulk_never_grows_consent(self):
        a,b,c=row('a',1),row('b',2),row('c',3)
        old=output([a,b])['body'].replace('- [ ] Approve all','- [x] Approve all')
        refreshed=output([a,b,c],previous_body=old,**authenticated())
        self.assertEqual([item['id'] for item in refreshed['preserved']],['a','b'])
        self.assertIn('- [ ] Approve all',refreshed['body'])
        self.assertIn('- [ ] New 3',refreshed['body'])
        planned=plan(refreshed['body'],label='question',records=[a,b,c],decisions=[],sender='teacher',permission='write',comment_author='ctm[bot]',bot_login='ctm[bot]',head_repository_id=1,base_repository_id=1)
        self.assertEqual([item['id'] for item in planned['decisions']],['a','b'])

    def test_changed_gone_and_recorded_ticks_are_reported_without_boxes(self):
        a,b=row('a',1),row('b',2)
        old=output([a,b])['body'].replace('- [ ] Approve all','- [x] Approve all')
        changed=output([row('a',9)],previous_body=old,**authenticated())
        self.assertEqual(changed['preserved'],[])
        self.assertEqual({item['id'] for item in changed['notCarried']},{'a','b'})
        recorded=output([a,b],[decision(a,1),decision(b,2,'rejected')],previous_body=old,**authenticated())
        self.assertEqual(recorded['recorded'],2)
        self.assertEqual(TOKEN.findall(recorded['body']),[])
        self.assertNotIn('- [',recorded['body'])
        self.assertEqual({item['reason'] for item in recorded['notCarried']},{'recorded'})

    def test_forged_comment_wrong_question_and_conflicting_ticks_fail_closed(self):
        a=row('a',1)
        body=output([a])['body'].replace('- [ ] New 1','- [x] New 1')
        for mutation in [dict(comment_author='stranger',bot_login='ctm[bot]'),dict(comment_author='',bot_login='')]:
            with self.subTest(mutation=mutation),self.assertRaises(VariantError):
                reconcile(body,label='question',records=[a],decisions=[],**mutation)
        for wrong in [body.replace(question_marker('question'),question_marker('other')),
                      body+'\n- [x] '+token('question','a','b'*16), body+'\n- [x] missing token']:
            with self.subTest(wrong=wrong),self.assertRaises(VariantError):
                reconcile(wrong,label='question',records=[a],decisions=[],**authenticated())

    def test_moved_recorded_decision_reports_current_and_historical_locators(self):
        old,current=row('old',1),row('current',1)
        for candidate in [old,current]:
            previous=output([candidate])['body'].replace('- [ ] New 1','- [x] New 1')
            refreshed=output([current],[decision(old,4)],previous_body=previous,**authenticated())
            self.assertEqual(refreshed['preserved'],[])
            self.assertEqual(refreshed['notCarried'][0]['reason'],'recorded')
            self.assertEqual(refreshed['recorded'],1)
            self.assertNotIn('- [',refreshed['body'])

    def test_bulk_refresh_carries_only_current_passes_and_clears_regressed_ticks(self):
        passing,failed,unknown=row('pass',1),row('fail',2,passed=False),row('unknown',3)
        unknown['tests']=[]
        records=[passing,failed,unknown]
        previous=output(records)['body'].replace('- [ ] Approve all','- [x] Approve all')
        refreshed=output(records,previous_body=previous,**authenticated())
        self.assertEqual([item['id'] for item in refreshed['preserved']],['pass'])
        self.assertEqual({item['id'] for item in refreshed['notCarried']},{'fail','unknown'})
        self.assertEqual({item['reason'] for item in refreshed['notCarried']},{'not passing'})
        planned=plan(refreshed['body'],label='question',records=records,decisions=[],sender='teacher',permission='write',comment_author='ctm[bot]',bot_login='ctm[bot]',head_repository_id=1,base_repository_id=1)
        self.assertEqual([item['id'] for item in planned['decisions']],['pass'])
        previous=output([passing])['body'].replace('- [ ] New 1','- [x] New 1')
        regressed=row('pass',1,passed=False)
        self.assertEqual(regressed['hash'],passing['hash'])
        refreshed=output([regressed],previous_body=previous,**authenticated())
        self.assertEqual(refreshed['preserved'],[])
        self.assertEqual(refreshed['notCarried'][0]['reason'],'not passing')

    def test_unsafe_preview_urls_and_resource_overflow_fail_instead_of_truncating(self):
        a=row('a',1)
        for url in ['javascript:bad','https://user@preview.test/x','https://preview.test/x)\n- [x] attack','https://preview.test/`x`']:
            with self.subTest(url=url),self.assertRaises(VariantError):
                render(label='question',records=[a],decisions=[],cards={'a':url})
        with self.assertRaisesRegex(VariantError,'budget'):
            output([row('a',1,note='x'*60000)])


if __name__=='__main__':unittest.main()
