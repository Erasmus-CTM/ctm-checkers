"""The common producer can admit another engine without importing SymPy."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_structural_stack_import_does_not_load_sympy():
    # A fresh process catches accidental eager imports hidden by other tests.
    code='''import sys
sys.path.insert(0,sys.argv[1])
from ctm_checkers.stack.importer import import_xml
assert not any(n=="sympy" or n.startswith("sympy.") for n in sys.modules)
import ctm_checkers.stack as stack
assert {"parse","answer_test","Node"} <= set(dir(stack))
assert stack.parse("x+1") is not None
assert "sympy" in sys.modules
'''
    subprocess.run([sys.executable,'-I','-c',code,str(ROOT/'src')],check=True)


def test_supplied_backend_is_closed_when_common_request_validation_fails():
    sys.path.insert(0,str(ROOT/'authoring'))
    from ctm_variants.stack_component import request
    class Backend:
        id='maxima'
        entered=False
        exited=False
        def __enter__(self):self.entered=True;return self
        def __exit__(self,*error):self.exited=True
        def seed_record(self,*args,**kwargs):raise AssertionError('Should not execute')
        propose=card_data=seed_record
    backend=Backend()
    with pytest.raises(ValueError,match='request/version'):
        request({'version':999},backend=backend)
    assert backend.entered and backend.exited
