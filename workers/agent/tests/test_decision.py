"""Tests for the domain Decision module (domain/decision.py)
plus the Jev adapter merge logic (adapters/jev.py, pure) and workflow routing.

Run:  python3 -m unittest tests.test_decision -v   (from workers/agent/)
No Supabase, no HTTP, no mocks — the interface is the test surface.
(Jev tests patch the key constant; ask_jev never touches the network.)
"""
import os
import sys
import unittest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token-1234")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters import jev  # noqa: E402
import workflow.edges as edges  # noqa: E402
from domain.decision import (  # noqa: E402
    approve_execution,
    build_proposals,
    decide_from_data,
    matches,
    path_of,
    percentile,
    run_decision,
    within_window,
)
from domain.criticality import bob_criticality, criticality_from_inventory  # noqa: E402
from adapters.jev import ask_jev, build_questions, merge_verdict, summarize_traffic  # noqa: E402
from workflow.edges import should_assess  # noqa: E402

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


def _jev_escalate(conf=0.9, regressing=(("checkout", 0.93),)):
    answers = {"verdict": {"type": "choice", "choice": "escalate",
                           "probabilities": {"escalate": conf, "keep": 1 - conf},
                           "confidence": conf}}
    for ep, p in regressing:
        answers[f"{ep}_regressing"] = {"type": "noul", "noul": p}
    return answers


def _jev_keep(conf=0.85):
    return {"verdict": {"type": "choice", "choice": "keep",
                        "probabilities": {"escalate": 1 - conf, "keep": conf},
                        "confidence": conf}}


class TestJevMerge(unittest.TestCase):
    def test_unavailable_passes_rules_through(self):
        v, reasons = merge_verdict("escalate", ["canary 5xx on critical /checkout"], None)
        self.assertEqual(v, "escalate")
        self.assertTrue(any("jev: unavailable" in r for r in reasons))

    def test_agree_escalates_with_both_sources(self):
        v, reasons = merge_verdict("escalate", ["r1"], _jev_escalate())
        self.assertEqual(v, "escalate")
        self.assertTrue(any(r.startswith("rules:") for r in reasons))
        self.assertTrue(any(r.startswith("jev:") for r in reasons))
        self.assertFalse(any("disagree" in r for r in reasons))

    def test_jev_only_signal_still_escalates_labeled(self):
        # Human gate stays final: surfaced, labeled, needs proposal approval.
        v, reasons = merge_verdict("keep", ["no critical diff"], _jev_escalate())
        self.assertEqual(v, "escalate")
        self.assertTrue(any("disagree" in r for r in reasons))

    def test_rules_only_signal_escalates_labeled(self):
        v, reasons = merge_verdict("escalate", ["r1"], _jev_keep())
        self.assertEqual(v, "escalate")
        self.assertTrue(any("disagree" in r for r in reasons))

    def test_agree_keep(self):
        v, reasons = merge_verdict("keep", ["no critical diff"], _jev_keep())
        self.assertEqual(v, "keep")

    def test_malformed_answers_default_keep(self):
        v, _ = merge_verdict("keep", ["no critical diff"], {"verdict": {"choice": "maybe"}})
        self.assertEqual(v, "keep")


class TestJevClient(unittest.TestCase):
    def test_no_key_never_touches_network(self):
        real = jev.TYPESAFE_API_KEY
        jev.TYPESAFE_API_KEY = ""
        try:
            self.assertIsNone(ask_jev("state", {"verdict": {}}))
        finally:
            jev.TYPESAFE_API_KEY = real

    def test_empty_questions_short_circuits(self):
        self.assertIsNone(ask_jev("state", {}))

    def test_summary_and_questions_shape(self):
        rows = [row("stable", "/checkout", 200), row("canary", "/checkout", 500)]
        crit = {"critical": ["/checkout"], "high": ["/search"]}
        summary = summarize_traffic(rows, crit)
        self.assertIn("/checkout", summary)
        self.assertIn("stable", summary)
        q = build_questions(crit)
        self.assertEqual(q["verdict"]["type"], "choice")
        self.assertIn("checkout_regressing", q)
        self.assertEqual(q["checkout_regressing"]["type"], "noul")


class TestWorkflowRouting(unittest.TestCase):
    def test_skips_assess_without_key(self):
        real = edges.TYPESAFE_API_KEY
        edges.TYPESAFE_API_KEY = ""
        try:
            self.assertEqual(should_assess({"windowed": [{"a": 1}]}), "merge")
        finally:
            edges.TYPESAFE_API_KEY = real

    def test_skips_assess_without_rows(self):
        self.assertEqual(should_assess({"windowed": []}), "merge")


class TestTargetCriticality(unittest.TestCase):
    def test_methods_map_to_tiers(self):
        inv = [
            {"method": "POST", "path_template": "/checkout"},
            {"method": "GET", "path_template": "/search"},
            {"method": "DELETE", "path_template": "/users/{id}"},
        ]
        crit = criticality_from_inventory(inv)
        self.assertIn("/checkout", crit["critical"])
        self.assertIn("/search", crit["high"])
        # Templated paths reduce to their static prefix for prefix-matching.
        self.assertIn("/users/", crit["critical"])
        self.assertEqual(crit["source"], "target-spec")

    def test_skips_bad_entries(self):
        crit = criticality_from_inventory([
            {"method": "GET", "path_template": "nope"},
            {"method": "GET", "path_template": "/ok"},
            "junk",
        ])
        self.assertEqual(crit, {"critical": [], "high": ["/ok"], "source": "target-spec"})

    def test_static_map_unchanged(self):
        crit = bob_criticality()
        self.assertIn("/checkout", crit["critical"])


if __name__ == "__main__":
    unittest.main()
