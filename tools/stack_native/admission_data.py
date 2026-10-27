"""Generate the pin-bound data for the shared JS expression admission.

Run after stack_input_data.py. This is a build/development tool; consumers
need neither Python nor SymPy to load the generated admission module.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ctm_checkers.stack import expressions as grammar, stack_data

TARGET = ROOT / 'src/ctm_checkers/stack/admission-data.json'


def generated():
    data = {'schema': 1, 'stackCommit': stack_data.STACK_COMMIT,
            'limits': {name: getattr(grammar, name) for name in
                       ('MAX_CHARS', 'MAX_TOKENS', 'MAX_DEPTH', 'MAX_DIGITS')},
            'functions': sorted(grammar._AUTHOR_FUNCTIONS),
            'logic': grammar.LOGIC_OPERATORS,
            'logicPrecedence': grammar.LOGIC_PRECEDENCE}
    for name in ('READABLE', 'UNREADABLE', 'CALLABLE', 'TRIG_FUNCTIONS',
                 'GLOBALLY_FORBIDDEN', 'VARIABLES', 'FUNCTIONS', 'REPLACEMENTS'):
        value = getattr(stack_data, name)
        data[name] = sorted(value) if isinstance(value, frozenset) else value
    return json.dumps(data, ensure_ascii=True, indent=2) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    options = parser.parse_args()
    text = generated()
    if options.check:
        if TARGET.read_text(encoding='utf-8') != text:
            parser.exit(1, 'Shared admission data is stale; run tools/stack_native/admission_data.py\n')
    else:
        TARGET.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
