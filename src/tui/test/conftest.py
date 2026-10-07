"""
Makes `lib` importable when pytest runs without a sourced workspace.

Once the workspace is built, `install/setup.bash` puts `lib` on the path and this is a
no-op. It only matters for running the tests straight out of the source tree.
"""

import sys
from pathlib import Path

LIB_PACKAGE = Path(__file__).resolve().parents[2] / "lib"

if str(LIB_PACKAGE) not in sys.path:
    sys.path.insert(0, str(LIB_PACKAGE))
