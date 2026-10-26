"""The STACK golden tables' answers, validated by native STACK (its PHP input
validation, validation.php) and compared with ctm_checkers.stack's verdicts
and messages in the tables: those that name a question or feedback variable
(S-01), and every answer for STACK's rules for the text of an answer (S-13).

    python tools/stack_native/check_validation.py --stack-source STACK [--out FILE]

STACK forbids a student the names that the question variables write
(question.php:430-442, cassecurity.class.php:373-376) with the validation
error "Forbidden variable or constant: …" (answer note forbiddenVariable).
For every input of a `stack.answer` row whose answer names such a variable
(PHP 8 and STACK at the commit of native-stack.yml; no Maxima: validation
is STACK's PHP side):

- agree: both invalid, with the same message (STACK's markup removed);
- agree, other message: both invalid with STACK's forbiddenVariable, but
  STACK's message names other names of the answer: the unknown names of
  three letters or more (S-13, in ctm_checkers.stack since 0.6.0);
- feedback variable: the answer names only a PRT's feedback variable;
  ctm_checkers.stack forbids it (S-01), because its answer tests evaluate the
  student's expression where the feedback variables are defined; listed apart,
  not part of the comparison;
- disagree: anything else (the command fails).

S-13, every input of a `stack.answer` row (not empty):

- agree: both valid, or both invalid with the same message where STACK's
  error is one of the rules S-13 follows (names of three letters or more,
  case, In, characters, spaces, a comma between terms: STACK's answer notes
  forbiddenVariable, unknownVariableCase, unknownFunctionCase,
  stackCas_badLogIn, forbiddenChar, spaces, trigspace, unencapsulated_comma);
- agree, other message: both invalid, STACK's error one of those rules, with
  another message here (an answer that breaks two rules: STACK lists both);
- agree, other rule: both invalid, STACK's error another rule (a final `+`,
  a missing bracket, an apostrophe, missing stars), with this engine's message;
- after STACK's PHP: valid for STACK's PHP validation, invalid here by a rule
  of the CAS side (Maxima's 0^0; matrix and collection types, scalar
  arithmetic, numbers, lowest terms), which PHP alone does not decide;
- S-01 names: invalid here because the answer names a question or feedback
  variable, which this engine forbids (S-01); listed apart;
- other rule, valid here: invalid for STACK by a rule that S-13 does not take
  on (a forbidden word that is an operator: STACK forbids `+` in HELM's
  bodmas.xml), valid here; listed, as before S-13;
- disagree: anything else (the command fails).

Matrix inputs are validated as the expression typed (STACK's matrix input
validates each cell the same way).
"""
import argparse
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / 'src'))  # ctm_checkers from src/ unless one is importable (a wheel)
sys.path.insert(0, str(ROOT / 'tools'))
import golden
import golden_stack  # noqa: E402
from ctm_checkers.stack import engine  # noqa: E402
from ctm_checkers.stack.expressions import parse  # noqa: E402
from ctm_checkers.stack.importer import import_xml  # noqa: E402

FORBIDDEN = 'Forbidden variable or constant: '


def names_in(text, insertstars):
    try:
        tree = parse(text, insertstars=insertstars)
    except Exception:
        return []
    return [node.value for node in engine._walk(tree) if node.kind == 'name']


def cases():
    """(row, input, case) for every answer that names a question or feedback variable."""
    questions, variants = {}, {}
    for path in golden.table_files():
        if not path.relative_to(golden.GOLDEN).as_posix().startswith('stack/'):
            continue
        for row in golden.read_rows(path):
            if row['call'] != 'stack.answer':
                continue
            value = row['input']
            key = (value['file'], value.get('python_checkers'))
            if key not in questions:
                checkers = value.get('python_checkers')
                questions[key] = {q['name']: q for q in import_xml(ROOT / value['file'], **golden_stack.checker_options(value))}
            question = questions[key][value['question']]
            vkey = key + (value['question'], value['seed'])
            if vkey not in variants:
                variants[vkey] = engine.instantiate(question, value['seed'])
            written = set(variants[vkey]['env'])
            feedback = engine._author_names(question, {}) - written
            inputs = {item['name']: item for item in question['inputs']}
            for name, text in value['answers'].items():
                if name not in inputs:   # leak.py's answers name an input numerical-measurement.xml does not have
                    continue
                item = inputs[name]
                used = names_in(text, item.get('insertstars', 0))
                if not set(used) & (written | feedback):
                    continue
                yield row, name, {'raw': text, 'forbiddenkeys': sorted(written), 'insertstars': item.get('insertstars', 0),
                                  'forbidwords': item['forbidwords'], 'forbidfloat': bool(item['forbidfloat']), 'type': item['type'],
                                  'question_names': sorted(set(used) & written), 'feedback_names': sorted(set(used) & feedback)}


# STACK's answer notes of the rules S-13 follows (student_input).
S13_NOTES = {'forbiddenVariable', 'unknownVariableCase', 'unknownFunctionCase', 'stackCas_badLogIn', 'forbiddenChar', 'spaces',
             'trigspace', 'unencapsulated_comma'}
S13_MESSAGES = ('Forbidden variable or constant: ', 'Input is case sensitive: ', 'You have typed in the expression In.',
                'CAS commands may not contain', 'Illegal spaces found', 'A comma in your expression')


def all_cases():
    """(row, input, case, author names) for every input of a stack.answer row (not empty)."""
    questions, variants = {}, {}
    for path in golden.table_files():
        if not path.relative_to(golden.GOLDEN).as_posix().startswith('stack/'):
            continue
        for row in golden.read_rows(path):
            if row['call'] != 'stack.answer' or not isinstance(row['output'], dict) or 'inputs' not in row['output'].get('validate', {}):
                continue
            value = row['input']
            key = (value['file'], value.get('python_checkers'))
            if key not in questions:
                checkers = value.get('python_checkers')
                questions[key] = {q['name']: q for q in import_xml(ROOT / value['file'], **golden_stack.checker_options(value))}
            question = questions[key][value['question']]
            vkey = key + (value['question'], value['seed'])
            if vkey not in variants:
                variants[vkey] = engine.instantiate(question, value['seed'])
            written = sorted(variants[vkey]['env'])
            inputs = {item['name']: item for item in question['inputs']}
            for name, text in value['answers'].items():
                if name not in inputs or not str(text).strip() or name not in row['output']['validate']['inputs']:
                    continue
                item = inputs[name]
                yield row, name, {'raw': text, 'forbiddenkeys': written, 'insertstars': item.get('insertstars', 0),
                                  'forbidwords': item['forbidwords'], 'forbidfloat': bool(item['forbidfloat']), 'type': item['type']}, \
                    engine._author_names(question, variants[vkey]['env'])


def s13_kind(mine, theirs, author_names):
    stack_text = text_of(theirs['errors'])
    notes = set(theirs['notes'].split(' | ')) if theirs['notes'] else set()
    s13_mine = not mine['valid'] and mine['feedback'].startswith(S13_MESSAGES)
    if theirs['valid']:
        if mine['valid']:
            return 'agree'
        named = re.findall(r'Forbidden variable or constant: ([^ ]+)\.(?: |$)', mine['feedback'])
        if s13_mine and named and mine['feedback'] == ' '.join(f'Forbidden variable or constant: {n}.' for n in named) \
                and all(n in author_names for n in named):
            return 'S-01 names'
        return 'disagree' if s13_mine else 'after STACK\'s PHP'
    if mine['valid']:
        # STACK's error is a rule S-13 does not take on (forbidden words as
        # operators): reported, not a disagreement of S-13.
        return 'disagree' if notes & S13_NOTES else 'other rule, valid here'
    if notes & S13_NOTES:
        return 'agree' if mine['feedback'] == stack_text else 'agree, other message'
    return 'agree, other rule'


def native(stack, items):
    folder = Path(tempfile.mkdtemp(prefix='ctm-stack-validation-'))
    try:
        sample = (stack / 'api' / 'config_sample.txt').read_text(encoding='utf-8')
        config = re.sub(r'^\$CFG->dirroot = .*$', lambda m: f"$CFG->dirroot = {json.dumps(str(stack / 'api'))};", sample, flags=re.M)
        config = re.sub(r'^\$CFG->dataroot = .*$', lambda m: f"$CFG->dataroot = {json.dumps(str(folder / 'data'))};", config, flags=re.M)
        (folder / 'config.php').write_text(config, encoding='utf-8')
        (folder / 'data').mkdir()
        (folder / 'run').mkdir()
        fields = ('raw', 'forbiddenkeys', 'insertstars', 'forbidwords', 'forbidfloat', 'type')
        result = subprocess.run(['php', str(ROOT / 'tools' / 'stack_native' / 'validation.php'), str(stack)],
                                input=json.dumps([{key: item[key] for key in fields} for item in items]),
                                capture_output=True, text=True, cwd=folder / 'run')
        if result.returncode:
            raise SystemExit('validation.php failed:\n' + result.stdout[-2000:] + result.stderr[-2000:])
        return json.loads(result.stdout)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def text_of(errors):
    return html.unescape(re.sub(r'<[^>]+>', '', errors)).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--stack-source', type=Path, required=True, help='STACK checkout (native-stack.yml: .stack-upstream-reference)')
    parser.add_argument('--out', type=Path, help='write every comparison as JSON')
    options = parser.parse_args()
    found = list(cases())
    everything = list(all_cases())
    unique = {}
    for case in [case for _, _, case in found] + [case for _, _, case, _ in everything]:
        fields = {key: case[key] for key in ('raw', 'forbiddenkeys', 'insertstars', 'forbidwords', 'forbidfloat', 'type')}
        unique.setdefault(json.dumps(fields, sort_keys=True), fields)
    keys = list(unique)
    results = dict(zip(keys, native(options.stack_source.resolve(), [unique[key] for key in keys])))
    fields_of = lambda case: json.dumps({key: case[key] for key in ('raw', 'forbiddenkeys', 'insertstars', 'forbidwords', 'forbidfloat', 'type')},
                                        sort_keys=True)
    counts, report = {}, []
    for row, name, case in found:
        mine = row['output']['validate']['inputs'][name]
        theirs = results[fields_of(case)]
        stack_text = text_of(theirs['errors'])
        forbidden = 'forbiddenVariable' in theirs['notes'].split(' | ')
        mine_forbidden = not mine['valid'] and mine['feedback'].startswith(FORBIDDEN)
        if case['question_names']:
            if not (mine_forbidden and not theirs['valid'] and forbidden):
                kind = 'disagree'
            elif stack_text == mine['feedback']:
                kind = 'agree'
            else:
                kind = 'agree, other message'
        else:
            kind = 'feedback variable' if mine_forbidden and (theirs['valid'] or not forbidden) else 'disagree'
        counts[kind] = counts.get(kind, 0) + 1
        report.append({'kind': kind, 'suite': row['suite'], 'id': row['id'], 'file': row['input']['file'], 'seed': row['input']['seed'],
                       'input': name, 'answer': case['raw'], 'question_names': case['question_names'],
                       'feedback_names': case['feedback_names'], 'ctm_checkers': mine,
                       'stack': {'valid': theirs['valid'], 'errors': stack_text, 'notes': theirs['notes']}})
    s13_counts, s13 = {}, []
    for row, name, case, author_names in everything:
        mine = row['output']['validate']['inputs'][name]
        theirs = results[fields_of(case)]
        kind = s13_kind(mine, theirs, author_names)
        s13_counts[kind] = s13_counts.get(kind, 0) + 1
        s13.append({'kind': kind, 'suite': row['suite'], 'id': row['id'], 'file': row['input']['file'], 'seed': row['input']['seed'],
                    'input': name, 'answer': case['raw'], 'ctm_checkers': mine,
                    'stack': {'valid': theirs['valid'], 'errors': text_of(theirs['errors']), 'notes': theirs['notes']}})
    if options.out:
        options.out.parent.mkdir(parents=True, exist_ok=True)
        options.out.write_text(json.dumps({'S-01': report, 'S-13': s13}, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    for item in report:
        if item['kind'] in ('disagree', 'agree, other message'):
            print(f"S-01 {item['kind']}: {item['file']} seed {item['seed']} {item['input']}={item['answer']!r}: "
                  f"ctm-checkers {item['ctm_checkers']['feedback']!r}; STACK {item['stack']['errors']!r} ({item['stack']['notes']})")
    shown = set()
    for item in s13:
        key = (item['kind'], item['answer'], item['ctm_checkers']['feedback'], item['stack']['errors'])
        if item['kind'] in ('disagree', 'agree, other message', 'other rule, valid here') and key not in shown:
            shown.add(key)
            print(f"S-13 {item['kind']}: {item['file']} {item['input']}={item['answer']!r}: "
                  f"ctm-checkers {item['ctm_checkers']['feedback']!r}; STACK {item['stack']['errors']!r} ({item['stack']['notes']})")
    print(f'S-01: {len(report)} answers that name a question or feedback variable: '
          + ', '.join(f'{kind} {count}' for kind, count in sorted(counts.items())))
    print(f'S-13: {len(s13)} answers ({len(unique)} distinct with S-01\'s): '
          + ', '.join(f'{kind} {count}' for kind, count in sorted(s13_counts.items())))
    return 1 if counts.get('disagree') or s13_counts.get('disagree') else 0

if __name__ == '__main__':
    sys.exit(main())
