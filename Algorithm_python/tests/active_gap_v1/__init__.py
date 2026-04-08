from __future__ import annotations

import pathlib
from pkgutil import extend_path
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SRC_DIR = _ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

__path__ = extend_path(__path__, __name__)

