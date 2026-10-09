"""Pytest configuration and common fixtures."""

import os
import sys
from pathlib import Path

# Ensure SightLine root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set default MOCK environment for fast tests
os.environ.setdefault("MOCK", "1")
