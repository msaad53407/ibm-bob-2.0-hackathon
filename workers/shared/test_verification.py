"""Tests for the Verification spec (workers/shared/verification.py).

Run:  python3 -m unittest test_verification -v   (from workers/shared/)
Dependency-free: the spec is plain data.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verification import CASES, CRITICALITY, LATENCY_DEGRADATION_FACTOR, MIN_SAMPLES  # noqa: E402


class TestVerificationSpec(unittest.TestCase):
    def test_every_tier_endpoint_has_a_probe(self):
        probed = {path.split("?", 1)[0] for _, path, _ in CASES}
        for tier in ("critical", "high"):
            for ep in CRITICALITY[tier]:
                self.assertIn(ep, probed, f"{tier} endpoint {ep} has no probe case")

    def test_edge_inputs_present(self):
        paths = [(m, p) for m, p, _ in CASES]
        self.assertIn(("POST", "/checkout"), paths)
        bodies = [b for m, p, b in CASES if (m, p) == ("POST", "/checkout")]
        self.assertIn({}, bodies, "critical edge input {} must be probed")

    def test_thresholds_sane(self):
        self.assertGreater(LATENCY_DEGRADATION_FACTOR, 1.0)
        self.assertGreaterEqual(MIN_SAMPLES, 2)


if __name__ == "__main__":
    unittest.main()
