"""Tests for the Decision module interface in graph.py.

Run:  python3 -m unittest test_decision -v   (from workers/agent/)
No Supabase, no HTTP, no mocks — the interface is the test surface.
"""
import os
import sys
import unittest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-key")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graph import (  # noqa: E402
    approve_execution,
    build_proposals,
    decide_from_data,
    matches,
    path_of,
    percentile,
    run_decision,
    within_window,
)

NOW = "2026-09-26T12:00:00+00:00"


def row(service, endpoint, status=200, latency=10, ts=NOW):
    return {
        "timestamp": ts, "service": service, "endpoint": endpoint,
        "status_code": status, "latency_ms": latency,
    }


class TestMatching(unittest.TestCase):
    def test_path_strips_query(self):
        self.assertEqual(path_of("/search?q=edge"), "/search")

    def test_prefix_not_substring(self):
        self.assertTrue(matches("/search?q=e", "/search"))
        self.assertFalse(matches("/research?q=e", "/search"))

    def test_percentile_clamps(self):
        self.assertEqual(percentile([5], 0.95), 5)
        self.assertEqual(percentile([1, 2, 3], 0.95), 3)
        with self.assertRaises(ValueError):
            percentile([], 0.95)


class TestWindow(unittest.TestCase):
    def test_stale_rows_ignored(self):
        rows = [row("canary", "/checkout", 500, 5, "2026-09-25T10:00:00+00:00")]
        self.assertEqual(within_window(rows, NOW), [])


class TestDecision(unittest.TestCase):
    def test_keep_on_no_diff(self):
        rows = [
            row("stable", "/checkout", 200), row("canary", "/checkout", 200),
            row("stable", "/search?q=a", 200, 5), row("stable", "/search?q=b", 200, 6),
            row("canary", "/search?q=a", 200, 6), row("canary", "/search?q=b", 200, 7),
        ]
        self.assertEqual(run_decision(rows, {"critical": ["/checkout"], "high": ["/search"]}),
                         ("keep", ["no critical diff"]))

    def test_escalate_on_canary_5xx(self):
        rows = [row("stable", "/checkout", 400), row("canary", "/checkout", 500)]
        verdict, reasons = run_decision(rows, {"critical": ["/checkout"], "high": []})
        self.assertEqual(verdict, "escalate")
        self.assertTrue(any("5xx" in r for r in reasons))

    def test_no_escalate_when_both_5xx(self):
        rows = [row("stable", "/checkout", 500), row("canary", "/checkout", 500)]
        self.assertEqual(run_decision(rows, {"critical": ["/checkout"], "high": []})[0], "keep")

    def test_escalate_on_latency(self):
        rows = [
            row("stable", "/search?q=a", 200, 5), row("stable", "/search?q=b", 200, 6),
            row("canary", "/search?q=a", 200, 800), row("canary", "/search?q=b", 200, 810),
        ]
        verdict, reasons = run_decision(rows, {"critical": [], "high": ["/search"]})
        self.assertEqual(verdict, "escalate")
        self.assertTrue(any("latency" in r for r in reasons))

    def test_latency_needs_min_samples(self):
        rows = [row("stable", "/search", 200, 5), row("canary", "/search", 200, 800)]
        self.assertEqual(run_decision(rows, {"critical": [], "high": ["/search"]})[0], "keep")

    def test_funnel_applies_window(self):
        rows = [
            row("stable", "/checkout", 200),
            row("canary", "/checkout", 500, 5, "2026-09-20T10:00:00+00:00"),
        ]
        self.assertEqual(decide_from_data(rows, {"critical": ["/checkout"], "high": []}, NOW)[0], "keep")


class TestProposals(unittest.TestCase):
    def test_keep_yields_none(self):
        self.assertEqual(build_proposals("keep", ["no critical diff"]), [])

    def test_5xx_yields_executable_flip_first(self):
        props = build_proposals("escalate", ["canary 5xx on critical /checkout: 1 vs stable 0"])
        self.assertEqual(props[0]["execute"], {"target": "stable"})
        self.assertTrue(all(p["execute"] is not None for p in props) or len(props) == 1)

    def test_latency_only_adds_context_note(self):
        props = build_proposals("escalate", ["canary p95 latency on high /search: 800ms vs stable 5ms"])
        self.assertEqual(props[0]["execute"], {"target": "stable"})
        self.assertEqual(len(props), 2)
        self.assertIsNone(props[1]["execute"])


class TestApprovalGate(unittest.TestCase):
    def test_unknown_set_rejected(self):
        self.assertEqual(approve_execution(None, "stable"), "unknown proposal_id")

    def test_non_escalating_set_rejected(self):
        self.assertEqual(
            approve_execution({"verdict": "keep", "proposals": []}, "stable"),
            "proposal set did not escalate",
        )

    def test_unapproved_target_rejected(self):
        funding = {"verdict": "escalate", "proposals": [
            {"action": "traffic flip to stable", "execute": {"target": "stable"}},
        ]}
        self.assertIsNone(approve_execution(funding, "stable"))
        self.assertIn("not in approved proposals",
                      approve_execution(funding, "canary") or "")

    def test_informational_only_set_rejects_flip(self):
        funding = {"verdict": "escalate", "proposals": [
            {"action": "investigate", "execute": None},
        ]}
        self.assertIn("not in approved proposals",
                      approve_execution(funding, "stable") or "")


if __name__ == "__main__":
    unittest.main()
