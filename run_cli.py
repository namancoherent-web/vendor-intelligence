#!/usr/bin/env python3
"""Run pipeline from project root: python run_cli.py "your query" """

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from vendor_intel.main import main

if __name__ == "__main__":
    main()
