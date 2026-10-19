import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# tools/golden.py and tools/build.py are imported by their tests.
sys.path.insert(0, str(ROOT / 'tools'))
# The package under test: src/, or a built wheel (CTM_CHECKERS_WHEEL).
PACKAGE = os.environ.get('CTM_CHECKERS_WHEEL') or str(ROOT / 'src')
sys.path.insert(0, PACKAGE)
