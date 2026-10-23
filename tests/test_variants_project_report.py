"""Synthetic scale and fake API checks; no authored grading or live GitHub IO."""
import copy
import contextlib
import io
import json
import os
from unittest.mock import patch
import sys
import tempfile
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'authoring'))
from ctm_variants import history
from ctm_variants.bot import TOKEN, token
from ctm_variants.checklist import question_marker
from ctm_variants.github_bot import Recorder
from ctm_variants.model import candidate, snapshot, VariantError
from ctm_variants.project_report import SUMMARY, RETIRED, archive, question_label, write_step_summary

HEAD, BASE = 'a' * 40, 'b' * 40
PATHS = ['.github/workflows/variants.yml', '.github/scripts/ctm-variants-records.py', '.github/ctm-variants.json']


def question(label):
    row = candidate('id-' + label, snapshot(['1'], {'Answer': '1'}, {}), tests={'passed': True})
    value = history.append_proposals(history.empty(label), [{'record': row, 'tape': []}])
    from ctm_variants.review import card_id
    return dict(label=label, path='_variants/' + label + '.yml', baseHash=None, manifest=value,
                records=[row], cards={row['id']: 'https://preview.test/' + label + '.html#' + card_id(row['id'])})


class API:
    def __init__(self): self.comments = {}; self.mutations = []; self.reads = {}; self.tick_on_second = None
    def request(self, method, path, value=None):
        if method == 'GET' and '/comments?per_page=' in path:
            return list(copy.deepcopy(self.comments).values())
        if method == 'GET' and '/issues/comments/' in path:
            identifier = int(path.rsplit('/', 1)[1]); self.reads[identifier] = self.reads.get(identifier, 0) + 1
            if self.tick_on_second == identifier and self.reads[identifier] == 2:
                self.comments[identifier]['body'] = self.comments[identifier]['body'].replace('- [ ]', '- [x]')
                self.comments[identifier]['updated_at'] = 'later'
            return copy.deepcopy(self.comments[identifier])
        if method == 'POST': identifier = max([0, *self.comments]) + 1
        elif method == 'PATCH': identifier = int(path.rsplit('/', 1)[1])
        else: raise AssertionError((method, path))
        self.mutations.append((method, path, copy.deepcopy(value)))
        saved = dict(id=identifier, body=value['body'], updated_at='now', user={'login': 'ctm[bot]'},
                     issue_url='https://api.github.com/repos/org/course/issues/7')
        self.comments[identifier] = saved
        return copy.deepcopy(saved)
    def comment(self, identifier, body, *, login='ctm[bot]'):
        self.comments[identifier] = dict(id=identifier, body=body, updated_at='before', user={'login': login},
            issue_url='https://api.github.com/repos/org/course/issues/7')


class Harness(Recorder):
    def __init__(self, questions):
        super().__init__(API(), repository='org/course', bot_login='ctm[bot]', producer_paths=PATHS)
        self.questions = questions; self.fail_label = None
    def _head(self, number, expected=None):
        if expected is not None and expected != HEAD: raise VariantError('head moved')
        return {'head': {'sha': HEAD}}
    def _producer(self, pull): return BASE
    def _records(self, pull, number, trusted_base, run_id=None):
        assert run_id == 20
        return {'questions': self.questions}
    def _value(self, question, head):
        if question['label'] == self.fail_label: raise VariantError('bad current lease')
        return history.validate(question['manifest'])


class ProjectReportTests(unittest.TestCase):
    def test_30_uses_question_comments_31_uses_one_summary_and_retains_current_ticks(self):
        small = Harness([question('q' + str(i)) for i in range(30)])
        self.assertFalse(small.refresh_preview(7, run_id=20)['project']['large'])
        self.assertEqual(len(small.api.mutations), 30)
        large = Harness([question('q' + str(i)) for i in range(31)])
        old = question_marker('q0') + '\n- [x] pending ' + token('q0', 'id-q0', large.questions[0]['records'][0]['hash'])
        large.api.comment(40, old)
        result = large.refresh_preview(7, run_id=20)
        self.assertTrue(result['project']['large']); self.assertEqual(len(large.api.mutations), 1)
        self.assertEqual(large.api.comments[40]['body'], old)
        summary = large.api.comments[result['project']['summaryCommentId']]['body']
        self.assertIn(SUMMARY, summary); self.assertIn('31 question(s)', summary)
        self.assertEqual(summary.count('[Review]('), 31)
        self.assertIn('preserve unrecorded ticks', summary)
        large.refresh_preview(7, run_id=20)
        self.assertEqual(len(large.api.mutations), 1, 'unchanged summary is idempotent')

    def test_deleted_question_archives_latest_intent_and_disables_tokens(self):
        bot = Harness([])
        old = question_marker('deleted') + '\n- [ ] pending ' + token('deleted', 'old', 'a' * 16)
        bot.api.comment(2, old); bot.api.comment(3, question_marker('not-ours'), login='someone')
        bot.api.tick_on_second = 2
        result = bot.refresh_preview(7, run_id=20)
        body = bot.api.comments[2]['body']
        self.assertEqual(result['project']['retired'], {'deleted': 2})
        self.assertIn(RETIRED, body); self.assertIn('- [x] pending', body)
        self.assertIn('not recorded', body); self.assertIsNone(question_label(body)); self.assertFalse(TOKEN.search(body))
        self.assertEqual(bot.api.comments[3]['body'], question_marker('not-ours'))
        bot.refresh_preview(7, run_id=20)
        self.assertEqual(len(bot.api.mutations), 1)

    def test_all_proofs_precede_writes_and_ambiguous_or_summary_consent_is_preserved(self):
        bot = Harness([question('q0'), question('q1')]); bot.fail_label = 'q1'
        bot.api.comment(2, question_marker('deleted'))
        with self.assertRaises(VariantError): bot.refresh_preview(7, run_id=20)
        self.assertEqual(bot.api.mutations, [])
        for body in (question_marker('q0') + question_marker('deleted'), SUMMARY + '\n- [x] preserve my intent', SUMMARY + '\n/variants reject q 1 \"keep this request\"'):
            bot = Harness([question('q0')]); bot.api.comment(2, body)
            with self.assertRaises(VariantError): bot.refresh_preview(7, run_id=20)
            self.assertEqual(bot.api.mutations, []); self.assertEqual(bot.api.comments[2]['body'], body)

    def test_checklist_uses_shared_validated_fraction_projection_and_keeps_input(self):
        from ctm_variants.checklist import render
        q = question('q')
        row = candidate('id-q', snapshot(['1/3', '2'], {'Answer': '1/3', 'Other': '2'}, {}), tests={'passed': True})
        q['records'] = [row]
        projection = {'mathml': '<math><mfrac><mn>1</mn><mn>3</mn></mfrac></math>', 'latex': r'\frac{1}{3}'}
        body = render(label='q', records=q['records'], decisions=[], cards=q['cards'],
                      teacher_displays={row['id']: {'Answer': projection}})['body']
        self.assertIn(r'$`\frac{1}{3}`$', body)
        self.assertIn('(input 1/3)', body)
        self.assertIn('Other', body)
        blank = dict(projection, latex='')
        fallback = render(label='q', records=q['records'], decisions=[], cards=q['cards'], teacher_displays={row['id']: {'Answer': blank}})['body']
        self.assertNotIn('rendered teacher', fallback)
        self.assertIn('teacher', fallback)
        with self.assertRaises(VariantError):
            render(label='q', records=q['records'], decisions=[], cards=q['cards'],
                   teacher_displays={row['id']: {'unknown': projection}})
        with self.assertRaises(VariantError):
            render(label='q', records=q['records'], decisions=[], cards=q['cards'],
                   teacher_displays={row['id']: {'Answer': {'mathml': '<script>bad</script>', 'latex': 'bad'}}})

    def test_producer_check_writes_success_and_failure_job_summary_without_grading(self):
        from ctm_variants.producer import main
        context = dict(headSha=HEAD, producerSha=BASE, event='workflow_dispatch', expectedHead=HEAD,
                       runId=20, repositoryId=1, pullRequest=7)
        trusted = Path(__file__).resolve().parents[1]
        for approved in (False, True):
            with self.subTest(approved=approved), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); project = root / 'authored'; project.mkdir()
                output = root / 'output'; output.mkdir()
                q = question('q')
                if approved:
                    q['manifest'] = history.decision(q['manifest'], q['records'], q['records'][0]['id'], 'approved')
                (output / 'variants-records.json').write_text(json.dumps(dict(context, version=1, questions=[q])))
                (root / 'event.json').write_text('{}')
                summary_path = root / 'summary.md'
                with patch.dict(os.environ, {'GITHUB_TOKEN': 'fake', 'GITHUB_EVENT_PATH': str(root / 'event.json'),
                        'GITHUB_STEP_SUMMARY': str(summary_path)}, clear=False), \
                     patch('ctm_variants.producer.verify_context', return_value=context), \
                     patch('ctm_variants.producer.subprocess.check_output', return_value=HEAD), \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    status = main(['--project', str(project), '--trusted', str(trusted), '--output', str(output), '--check'])
                self.assertEqual(status, 0 if approved else 1)
                text = summary_path.read_text()
                self.assertIn('Approval check passed' if approved else 'Approval check failed', text)
                self.assertIn('| q |', text)

    def test_markdown_summary_escapes_authored_text_and_retirement_is_read_only(self):
        q = question('q'); q['label'] = 'author\n- [x] <script>|inject'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'summary.md'
            write_step_summary({'questions': [q]}, state='Passed\n- [x] forged', path=path)
            text = path.read_text()
            self.assertIn('| Question |', text); self.assertIn('&lt;script&gt;', text)
            self.assertNotIn('\n- [x]', text); self.assertNotIn('<script>', text)
        original = '```\n<script>code</script>\n' + question_marker('deleted')
        saved = archive('deleted', original, head=HEAD, run_id=20)
        self.assertIn('<script>code</script>', saved)
        self.assertIn('````', saved); self.assertIsNone(question_label(saved))


if __name__ == '__main__': unittest.main()
