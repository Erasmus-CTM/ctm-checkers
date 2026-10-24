#!/usr/bin/env python3
"""Run only from a trusted base checkout; never from the PR source tree."""
import sys
if not sys.flags.isolated:
    import os
    os.execv(sys.executable, [sys.executable, "-I", __file__] + sys.argv[1:])
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctm_variants.github_bot import main
if __name__ == "__main__":
    sys.exit(main())
