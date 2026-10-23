#!/usr/bin/env python3
"""Unprivileged records producer; execute only the trusted default checkout."""
import sys
if not sys.flags.isolated:
    import os
    os.execv(sys.executable, [sys.executable, "-I", __file__] + sys.argv[1:])
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctm_variants.producer import main
if __name__ == "__main__":sys.exit(main())
