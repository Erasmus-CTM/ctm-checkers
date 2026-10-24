"""Bounded neutral project reporting; no grading or authored source execution."""
import base64
import json
import re
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
from ctm_variants.checklist import QUESTION, _inline, _url, _pending, question_marker
from ctm_variants.model import VariantError, classify

SUMMARY = '<!-- ctm-variants-project-summary:v1 -->'
RETIRED = '<!-- ctm-variants-retired-question:v1 -->'
MAX_BODY = 60000


def question_label(body):
    """Decode only one canonical owned question marker; ambiguous intent fails."""
    tokens = QUESTION.findall(body)
    if not tokens:
        return None
    if len(tokens) != 1 or SUMMARY in body or RETIRED in body:
        raise VariantError('ambiguous owned variant comment markers')
    try:
        value = json.loads(base64.urlsafe_b64decode(tokens[0] + '=' * (-len(tokens[0]) % 4)))
    except (ValueError, UnicodeError) as error:
        raise VariantError('invalid owned question marker') from error
    label = value.get('label') if type(value) is dict and set(value) == {'label'} else None
    if (not isinstance(label, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', label)
            or '..' in label or question_marker(label) != '<!-- ctm-question:' + tokens[0] + ' -->'):
        raise VariantError('invalid owned question label')
    return label


def facts(question):
    entries, records = question['manifest']['decisions'], question['records']
    classified = classify(entries, records)
    pending, _ = _pending(question['label'], records, entries)
    gone = sum(row['state'] == 'gone' and row['entry']['status'] == 'approved' for row in classified['entries'])
    approved = sum(row['state'] in ('current', 'moved') and row['entry']['status'] == 'approved' for row in classified['entries'])
    passed = sum(type(record.get('tests')) is dict and record['tests'].get('passed') is True for record in records)
    card = next(iter(question.get('cards', {}).values()), None)
    if card:
        parsed = urlsplit(_url(card))
        card = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
    return {'label': question['label'], 'approved': approved, 'pending': len(pending),
            'gone': gone, 'passed': passed, 'records': len(records), 'url': card}


def table(questions, *, budget=45000):
    rows = ['| Question | Current approvals | Needs decision | Gone approvals | Passing checks | Review |',
            '| --- | ---: | ---: | ---: | --- | --- |']
    omitted = 0
    for question in questions:
        row = facts(question)
        link = '[Review](' + quote(row['url'], safe=':/?#@!$&*+,;=%-._~') + ')' if row['url'] else 'No current candidate'
        line = '| {} | {} | {} | {} | {}/{} | {} |'.format(_inline(row['label']), row['approved'],
            row['pending'], row['gone'], row['passed'], row['records'], link)
        if len(('\n'.join(rows) + '\n' + line).encode()) > budget:
            omitted += 1
        else:
            rows.append(line)
    if omitted:
        rows += ['', '{} further question(s) omitted from this bounded table; use the review artifacts.'.format(omitted)]
    return '\n'.join(rows)


def summary(questions, *, head, run_id, run_url):
    open_count = sum(bool(row['pending'] or row['gone']) for row in map(facts, questions))
    body = SUMMARY + '\n### Variant review summary\n\n'
    body += '{} question(s) need a decision. Open a review page for current candidates.\n\n'.format(open_count)
    body += table(questions)
    body += ('\n\nExisting per-question checklists are retained to preserve unrecorded ticks. '
             'Their recording still verifies the exact current head, candidate hashes and permission. '
             'No new per-question comments are created while more than 30 questions need decisions.\n\n')
    body += 'Evidence: head `' + head + '`; [records run ' + str(run_id) + '](' + _url(run_url) + ').'
    if len(body.encode()) > MAX_BODY:
        raise VariantError('project summary exceeds comment budget')
    return body


def archive(label, body, *, head, run_id):
    """Preserve the latest checklist as inert text, including unrecorded ticks."""
    inert = body.replace('<!-- ctm-', '< !-- ctm-')
    fence = '`' * max(3, max((len(run) + 1 for run in re.findall(r'`+', inert)), default=3))
    result = (RETIRED + '\n### Retired question: ' + _inline(label)
        + '\n\nThis question is absent from the current source. Old ticks and rejection commands below are **not recorded** and cannot be used here. '
          'Restore the question and rebuild review before making a current decision. '
          'The latest previous checklist is retained read-only; token openers are spaced to disable them.\n\n'
        + fence + '\n' + inert + '\n' + fence
        + '\n\nRetired at head `' + head + '`; records run ' + str(run_id) + '.')
    if len(result.encode()) > MAX_BODY:
        raise VariantError('retired checklist exceeds comment budget; preserve its history manually before retrying')
    return result


def write_step_summary(envelope=None, *, state='Records produced; approval check is separate', path=None):
    """Append Markdown only to the trusted runner-provided summary file."""
    if path is None:
        import os
        path = os.environ.get('GITHUB_STEP_SUMMARY')
    if not path:
        return
    content = '## Variants\n\n' + _inline(state) + '\n\n'
    if envelope is not None:
        content += table(envelope['questions']) + '\n\n'
    with Path(path).open('a', encoding='utf-8') as output:
        output.write(content)


def sync_comments(recorder, *, number, questions, comments, head, trusted, pull, run_id):
    """Reconcile reporting only after the caller's complete neutral proof.

    Existing current question checklists remain untouched in summary mode: their
    pending consent is never silently migrated to newer/different candidates.
    """
    labels = {question['label'] for question in questions}
    by_label, summaries = {}, []
    for comment in comments:
        body = comment.get('body', '')
        label = question_label(body)
        if label is not None:
            if label in by_label:
                raise VariantError('duplicate own sticky comments for one question')
            by_label[label] = comment
        if SUMMARY in body:
            if body.count(SUMMARY) != 1:
                raise VariantError('ambiguous project summary markers')
            summaries.append(comment)
    if len(summaries) > 1:
        raise VariantError('duplicate own project summaries')
    # Validate every archived body and summary before the first write. The
    # latest comment is read again immediately before its individual update.
    deleted = []
    for label, comment in by_label.items():
        if label not in labels:
            current = recorder._comment(number, comment['id'])
            if question_label(current['body']) != label:
                raise VariantError('question comment changed before retirement')
            archive(label, current['body'], head=head, run_id=run_id)
            deleted.append((label, current))
    large = sum(bool(row['pending'] or row['gone']) for row in map(facts, questions)) > 30
    previous = recorder._comment(number, summaries[0]['id']) if summaries else None
    def summary_has_intent(body):
        return bool(re.search(r'^\s*(?:- \[[xX]\] |/variants(?:\s|$))', body, re.MULTILINE) or '<!-- ctm-variant:' in body
                    or '<!-- ctm-bulk:' in body or QUESTION.search(body))
    if previous and summary_has_intent(previous['body']):
        raise VariantError('project summary contains unrecorded decision intent; preserve it before refreshing')
    summary_body = summary(questions, head=head, run_id=run_id,
        run_url='https://github.com/' + recorder.repo + '/actions/runs/' + str(run_id)) if large or previous else None
    def gate():
        recorder._head(number, head)
        if recorder._producer(pull) != trusted:
            raise VariantError('trusted preview producer base moved')
    def confirmed(saved, body):
        if (saved.get('user', {}).get('login') != recorder.bot or saved.get('body') != body
                or type(saved.get('id')) is not int or saved['id'] < 1):
            raise VariantError('project comment response does not confirm the configured bot body')
        return saved['id']
    retired = {}
    for label, initial in deleted:
        gate()
        latest = recorder._comment(number, initial['id'])
        if question_label(latest['body']) != label:
            raise VariantError('question comment changed before retirement')
        body = archive(label, latest['body'], head=head, run_id=run_id)
        saved = recorder.api.request('PATCH', recorder.prefix + '/issues/comments/' + str(latest['id']), {'body': body})
        retired[label] = confirmed(saved, body)
    summary_id = None
    if summary_body is not None:
        gate()
        if previous:
            latest = recorder._comment(number, previous['id'])
            if SUMMARY not in latest['body'] or summary_has_intent(latest['body']):
                raise VariantError('project summary changed or contains unrecorded decision intent')
            saved = recorder.api.request('PATCH', recorder.prefix + '/issues/comments/' + str(latest['id']), {'body': summary_body}) if latest['body'] != summary_body else latest
        else:
            if any(SUMMARY in item.get('body', '') for item in recorder._own_comments(number)):
                raise VariantError('project summary appeared concurrently; retry refresh')
            saved = recorder.post('/issues/' + str(number) + '/comments', {'body': summary_body})
        summary_id = confirmed(saved, summary_body)
    return {'large': large, 'summaryCommentId': summary_id, 'retired': retired}
