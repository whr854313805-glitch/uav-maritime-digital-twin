#!/usr/bin/env python3
"""
Entry-point wrapper: delegates to src/download_geospatial.py

Usage:
    python3 scripts/download_geospatial.py
"""

import sys
import os

# Ensure project root is on the path regardless of how this is invoked
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Change working directory to project root so relative data/ paths resolve
os.chdir(PROJECT_ROOT)

from src.download_geospatial import main

if __name__ == "__main__":
    main()
