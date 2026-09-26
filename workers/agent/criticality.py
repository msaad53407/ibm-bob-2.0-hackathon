"""Doc-understanding node: bob-shell-backed criticality with file fallback."""
import json
import subprocess

import _paths  # noqa: F401 — ensures shared/ is importable
from verification import CRITICALITY as SPEC_CRITICALITY  # noqa: E402


def bob_criticality(spec_dir: str = "docs/spec"):
    """Genuinely bob-shell-backed with fallback so demo never blocks."""
    try:
        out = subprocess.run(
            ["bob-shell", "summarize", spec_dir, "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            return json.loads(out.stdout)
    except Exception:
        pass
    return {**SPEC_CRITICALITY, "source": "fallback"}
