"""Makes workers/shared/ importable in both layouts (no per-module duplication).

Docker:  /app/shared/          (COPY shared/*.py ./shared/)
Repo:    workers/shared/       (../shared relative to workers/traffic-runner/)
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (
    os.path.join(_HERE, "shared"),
    os.path.join(_HERE, "..", "shared"),
):
    _abs = os.path.normpath(os.path.abspath(_p))
    if os.path.isdir(_abs) and _abs not in sys.path:
        sys.path.insert(0, _abs)
