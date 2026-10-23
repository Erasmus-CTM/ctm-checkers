#!/usr/bin/env python3
"""Native review CLI; run as a file, never as a lesson-directory module."""
import sys

if not sys.flags.isolated:
    import os
    os.execv(sys.executable, [sys.executable, "-I", __file__] + sys.argv[1:])

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctm_variants.cli import main

if __name__ == "__main__":
    sys.exit(main())
