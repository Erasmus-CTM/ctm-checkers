"""Collect independent PHP + Maxima evidence for a golden-table revision.

This is an observation report, not an agreement gate. Every native difference,
exception and representation-only row remains visible for independent review.
It never imports CTM's implementation or uses a golden as a native answer.
"""
import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BASE = '9e042dc'
COMMITS = {'10d323311b7f39fb7b092dd10ce75f7d8632f525',
           '33383047af39c204bf4442802a058f8b918b2b1b'}


def git(*args, root=ROOT):
    return subprocess.check_output(['git', '-C', str(root), *args])


def rows(data):
    result = {}
    for line in data.decode('utf-8').splitlines():
        if line.strip():
            row = json.loads(line)
            if row['id'] in result:
                raise ValueError('duplicate golden row ' + row['id'])
            result[row['id']] = row
    return result


def inventory(base, head, root=ROOT):
    """Exact revision diff, including added and removed rows, without change tags."""
    names = sorted(set(git('ls-tree', '-r', '--name-only', base, 'tests/golden/stack', root=root).decode().splitlines()) |
                   set(git('ls-tree', '-r', '--name-only', head, 'tests/golden/stack', root=root).decode().splitlines()))
    selected = []
    for name in names:
        if not name.endswith('.jsonl'):
            continue
        sides = []
        for ref in (base, head):
            found = git('ls-tree', ref, '--', name, root=root).strip()
            sides.append(rows(git('show', ref + ':' + name, root=root)) if found else {})
        before, after = sides
        for key in sorted(before.keys() | after.keys()):
            old, new = before.get(key), after.get(key)
            if old == new:
                continue
            selected.append({'table': name, 'id': key,
                             'revision': 'added' if old is None else 'removed' if new is None else 'changed',
                             'before': old, 'after': new})
    if not selected:
        raise ValueError('no changed STACK rows: refusing an empty oracle report')
    return selected


def cases_for(entry, base, head, root=ROOT):
    row = entry['after'] or entry['before']
    ref = head if entry['after'] else base
    common = {'key': entry['table'] + ':' + entry['id'], 'call': row['call'], 'input': row['input']}
    if row['call'] == 'stack.answer_test':
        return [common]
    if row['call'] not in {'stack.answer', 'stack.tests', 'stack.import', 'stack.instantiate', 'stack.card'}:
        raise ValueError('unmapped native call: ' + row['call'])
    raw = git('show', ref + ':' + row['input']['file'], root=root)
    document = ET.fromstring(raw)
    questions = [q for q in document.findall('question') if q.attrib.get('type') == 'stack']
    wanted = row['input'].get('question')
    if wanted is not None:
        questions = [q for q in questions if q.findtext('name/text') == wanted]
    if not questions or (wanted is not None and len(questions) != 1):
        raise ValueError('question not uniquely found: ' + common['key'])
    result = []
    for index, question in enumerate(questions):
        quiz = ET.Element('quiz')
        quiz.append(question)
        xml = ET.tostring(quiz, encoding='unicode')
        result.append(dict(common, key=common['key'] + '#' + str(index), xml=xml,
                           fixture_sha256=hashlib.sha256(raw).hexdigest(),
                           question_sha256=hashlib.sha256(xml.encode()).hexdigest()))
    return result


def text(value):
    return ' '.join(html.unescape(re.sub('<[^>]*>', '', str(value or ''))).split())


def differences(entry, results):
    """Compare semantic fields; retain all raw fields in the report as evidence."""
    if entry['after'] is None:
        return [{'field': 'removed row', 'review': 'native observation retained; CTM now stops at import'}]
    row = entry['after']
    expected = row.get('output', row.get('by_python', {}).get('3.12'))
    if expected is None:
        return [{'field': 'golden output', 'review': 'no output for Python 3.12'}]
    failures = [{'field': 'native exception', 'native': item['exception']} for item in results if 'exception' in item]
    failures += [{'field': 'native runtimeerrors', 'native': item['observation']['runtimeerrors']}
                 for item in results if item.get('observation', {}).get('runtimeerrors')]
    if failures:
        return failures
    native = results[0]['observation']
    out = []

    def compare(field, mine, theirs):
        equal = abs(mine - theirs) <= 1e-9 if isinstance(mine, (int, float)) and isinstance(theirs, (int, float)) else mine == theirs
        if not equal:
            out.append({'field': field, 'ctm': mine, 'native': theirs})

    if row['call'] == 'stack.answer_test':
        if 'raised' in expected:
            return [{'field': 'CTM author error', 'ctm': expected, 'native': native}]
        # Native null is a failure to obtain a verdict, not a false verdict.
        compare('correct', expected['correct'], native['verdict'])
        compare('cas_valid', expected.get('cas_valid', expected.get('valid')), native['valid'])
        compare('feedback', text(expected.get('feedback')), text(native['feedback']))
        compare('note', expected.get('note', '').rstrip('. '), native['note'].rstrip('. '))
        if native.get('errors'):
            out.append({'field': 'native errors', 'native': native['errors']})
    elif row['call'] == 'stack.answer':
        grade = expected.get('grade', {})
        for name, item in expected.get('validate', {}).get('inputs', {}).items():
            if name not in native['inputs']:
                out.append({'field': 'missing native input', 'input': name})
                continue
            theirs = native['inputs'][name]
            compare(name + '.valid', item['valid'], theirs['status'] in {'valid', 'score'})
            compare(name + '.feedback', text(item.get('feedback')), text(theirs['errors']))
        if grade.get('status') == 'graded':
            compare('score', grade['score'], native['score'])
            for name, item in grade.get('prts', {}).items():
                if name not in native['prts']:
                    out.append({'field': 'missing native prt', 'prt': name})
                    continue
                theirs = native['prts'][name]
                compare(name + '.score', item['score'], theirs['score'])
                compare(name + '.branch_notes', item.get('notes', []), theirs['branch_notes'])
                compare(name + '.feedback', text(item.get('feedback')), text(theirs['feedback']))
                if theirs['errors']:
                    out.append({'field': name + '.errors', 'native': theirs['errors']})
        elif 'raised' in grade:
            out.append({'field': 'CTM author error', 'ctm': grade})
    elif row['call'] == 'stack.tests':
        mine = {str(item['testcase']): item for item in expected.get('results', [])}
        theirs = {str(item['testcase']): item for item in native['tests']}
        compare('testcases', sorted(mine), sorted(theirs))
        for key in sorted(mine.keys() & theirs.keys()):
            compare('testcase.' + key + '.passed', mine[key]['passed'], theirs[key]['result']['passed'])
    else:
        out.append({'field': 'representation', 'review': 'native initialisation recorded; CTM import/variant/card representation has no native equivalent'})
    return out


def config(stack, folder):
    sample = (stack / 'api/config_sample.txt').read_text(encoding='utf-8')
    # Native maximalocal.mac uses the Moodle path layout. Keep upstream untouched.
    link = folder / 'question/type/stack'
    link.parent.mkdir(parents=True)
    link.symlink_to(stack, target_is_directory=True)
    values = {'dirroot': str(folder), 'dataroot': str(folder / 'data'),
              'libdir': str(stack / 'api/emulation/libdir'), 'platform': 'linux',
              'maximaversion': '5.46.0', 'maximacommand': 'maxima',
              'supportedlanguages': 'en', 'casresultscache': 'none', 'castimeout': 30}
    # Append overrides after the unmodified upstream defaults.
    sample += '\n' + '\n'.join('$CFG->' + key + ' = ' + json.dumps(value) + ';' for key, value in values.items()) + '\n'
    (folder / 'config.php').write_text(sample, encoding='utf-8')
    (folder / 'run').mkdir()
    (folder / 'data').mkdir()
    for name in ('logs', 'plots', 'sitelibrary', 'tmp'):
        (folder / 'data/stack' / name).mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default=BASE)
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--stack-source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--inventory-only', action='store_true')
    args = parser.parse_args()
    base, head = (git('rev-parse', ref).decode().strip() for ref in (args.base, args.head))
    selected = inventory(base, head)
    cases = [case for entry in selected for case in cases_for(entry, base, head)]
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'base': base, 'head': head, 'rows': selected, 'case_count': len(cases)}
    (args.out / 'inventory.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if args.inventory_only:
        print(f'{len(selected)} revised rows; {len(cases)} native cases')
        return
    stack = args.stack_source.resolve()
    commit = git('rev-parse', 'HEAD', root=stack).decode().strip()
    if commit not in COMMITS or git('status', '--porcelain', '--untracked-files=no', root=stack).strip():
        raise SystemExit('native source must be an unmodified checkout of one of the two pinned STACK commits')
    runtime = subprocess.check_output(['maxima', '--version'], text=True).strip()
    if not re.search(r'\b5\.46\.0\b', runtime):
        raise SystemExit('Maxima 5.46.0 required: ' + runtime)
    report.update(stack_commit=commit, maxima=runtime, php=subprocess.check_output(['php', '--version'], text=True).strip())
    (args.out / 'requests.jsonl').write_text(''.join(json.dumps(case, ensure_ascii=False) + '\n' for case in cases), encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='ctm-native-question-') as temp:
        folder = Path(temp)
        config(stack, folder)
        with (args.out / 'requests.jsonl').open(encoding='utf-8') as source, (args.out / 'native.jsonl').open('w', encoding='utf-8') as target, \
                (args.out / 'php-stderr.log').open('w', encoding='utf-8') as errors:
            completed = subprocess.run(['php', str(Path(__file__).with_suffix('.php')), str(stack)],
                                       stdin=source, stdout=target, stderr=errors, cwd=folder / 'run', timeout=2400)
    if completed.returncode:
        raise SystemExit('native PHP process failed; inspect php-stderr.log and partial native.jsonl')
    observed = [json.loads(line) for line in (args.out / 'native.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    by_key = {item['key']: item for item in observed}
    if len(observed) != len(cases) or len(by_key) != len(cases) or set(by_key) != {case['key'] for case in cases}:
        raise SystemExit('missing, unexpected or duplicate native observation')
    counts = Counter()
    for entry in selected:
        linked = cases_for(entry, base, head)
        results = [by_key[case['key']] for case in linked]
        entry['native_keys'] = [case['key'] for case in linked]
        entry['differences'] = differences(entry, results)
        entry['review'] = 'required' if entry['differences'] else 'compared fields agree'
        counts[entry['review']] += 1
        print(json.dumps({'row': entry['table'] + ':' + entry['id'], 'revision': entry['revision'],
                          'native': results, 'differences': entry['differences']}, ensure_ascii=False), flush=True)
    report['summary'] = dict(counts)
    report['acceptance'] = 'Raw native evidence collected. Independent review of every difference is required; this is not an agreement gate.'
    (args.out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report['summary']))
    if any(item.get('harness_error') for item in observed):
        raise SystemExit('native PHP raised an implementation error; inspect observations before accepting this run')


if __name__ == '__main__':
    main()
