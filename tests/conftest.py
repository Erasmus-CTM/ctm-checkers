import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# tools/golden.py and tools/build.py are imported by their tests.
sys.path.insert(0, str(ROOT / 'tools'))
# The package under test: src/, or the built wheels (CTM_CHECKERS_WHEEL:
# ctm-checkers' wheel and, after os.pathsep, the STACK engine's).
PACKAGES = (os.environ.get('CTM_CHECKERS_WHEEL') or str(ROOT / 'src')).split(os.pathsep)
PACKAGE = PACKAGES[0]
for path in reversed(PACKAGES):
    sys.path.insert(0, path)
