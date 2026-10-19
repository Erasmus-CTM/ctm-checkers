import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# tools/golden.py is imported by the table tests.
sys.path.insert(0, str(ROOT / 'tools'))
