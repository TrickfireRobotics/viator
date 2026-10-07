"""
Puts `src/` on the path so `lib` imports resolve the same way they do at runtime, where
`scripts/launch.sh` sets PYTHONPATH.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
