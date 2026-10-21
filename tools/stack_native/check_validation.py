"""The STACK golden tables' answers that name a question or feedback variable
(S-01), validated by native STACK (its PHP input validation, validation.php)
and compared with ctm_checkers.stack's verdicts in the tables.

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
  three letters or more (S-13, not yet in ctm_checkers.stack);
- feedback variable: the answer names only a PRT's feedback variable;
  ctm_checkers.stack forbids it (S-01), because its answer tests evaluate the
  student's expression where the feedback variables are defined; listed apart,
  not part of the comparison;
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
import golden  # noqa: E402
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
                questions[key] = {q['name']: q for q in import_xml(ROOT / value['file'], python_checkers=ROOT / checkers if checkers else None)}
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
    unique = {}
    for _, _, case in found:
        unique.setdefault(json.dumps(case, sort_keys=True), case)
    keys = list(unique)
    results = dict(zip(keys, native(options.stack_source.resolve(), [unique[key] for key in keys])))
    counts, report = {}, []
    for row, name, case in found:
        mine = row['output']['validate']['inputs'][name]
        theirs = results[json.dumps(case, sort_keys=True)]
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
    if options.out:
        options.out.parent.mkdir(parents=True, exist_ok=True)
        options.out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    for item in report:
        if item['kind'] in ('disagree', 'agree, other message'):
            print(f"{item['kind']}: {item['file']} seed {item['seed']} {item['input']}={item['answer']!r}: "
                  f"ctm-checkers {item['ctm_checkers']['feedback']!r}; STACK {item['stack']['errors']!r} ({item['stack']['notes']})")
    print(f'{len(report)} answers that name a question or feedback variable ({len(unique)} distinct): '
          + ', '.join(f'{kind} {count}' for kind, count in sorted(counts.items())))
    return 1 if counts.get('disagree') else 0


if __name__ == '__main__':
    sys.exit(main())
