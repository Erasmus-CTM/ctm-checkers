#!/usr/bin/env python3
"""Copy to .github/scripts in the trusted course; no authored imports."""
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[2]
entry = root / "_extensions/ctm-checkers/native-authoring/ctm-variants-artifact.py"
os.execv(sys.executable, [sys.executable, "-I", str(entry), *sys.argv[1:]])
