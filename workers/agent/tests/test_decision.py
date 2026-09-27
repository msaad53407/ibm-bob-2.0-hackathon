"""Tests for the domain Decision module (domain/decision.py)
plus the Jev adapter merge logic (adapters/jev.py, pure) and workflow routing.

Run:  python3 -m unittest tests.test_decision -v   (from workers/agent/)
No Supabase, no HTTP, no mocks — the interface is the test surface.
(Jev tests patch the key constant; ask_jev never touches the network.)

Request pairing itself is covered by tests/test_compare.py.
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
from domain.compare import CANARY_ERROR, LATENCY_REGRESS, SHARED_ERROR  # noqa: E402
from domain.decision import (  # noqa: E402
    analyze,
    approve_execution,
    build_proposals,
    decide_from_data,
    describe,
    group_deltas,
    informational_proposals,
    matches,
    path_of,
    risk_of,
    within_window,
)
from domain.criticality import bob_criticality, criticality_from_inventory  # noqa: E402
from adapters.jev import ask_jev, build_questions, merge_verdict, summarize_traffic  # noqa: E402
from workflow.edges import should_assess  # noqa: E402

NOW = "2026-09-26T12:00:00+00:00"

CRIT = {"critical": ["/checkout"], "high": ["/search"]}


def row(service, method, path, status=200, latency=10, ts=NOW,
        label="happy-path", tier="critical", source="synth"):
    """One probe row as the runner writes it (post-0007/0008 shape)."""
    return {
        "timestamp": ts, "service": service, "endpoint": path,
        "status_code": status, "latency_ms": latency,
        "case_method": method, "case_label": label,
        "case_tier": tier, "case_source": source,
    }


def both(method, path, stable_status, canary_status, *, stable_latency=10,
         canary_latency=10, tier="critical", label="happy-path", repeats=1):
    """The same request fired at both sides, `repeats` times each."""
    return (
        [row("stable", method, path, stable_status, stable_latency, tier=tier, label=label)] * repeats
        + [row("canary", method, path, canary_status, canary_latency, tier=tier, label=label)] * repeats
    )


def analyze_rows(rows, crit=CRIT, **kw):
    return analyze(rows, crit, **kw)


class TestMatching(unittest.TestCase):
    def test_path_strips_query(self):
        self.assertEqual(path_of("/search?q=edge"), "/search")

    def test_prefix_not_substring(self):
        self.assertTrue(matches("/search?q=e", "/search"))
        self.assertFalse(matches("/research?q=e", "/search"))


class TestWindow(unittest.TestCase):
    def test_stale_rows_ignored(self):
        rows = [row("canary", "POST", "/checkout", 500, 5, "2026-09-25T10:00:00+00:00")]
        self.assertEqual(within_window(rows, NOW), [])


class TestAnalysis(unittest.TestCase):
    def test_keep_on_no_diff(self):
        result = analyze_rows(both("POST", "/checkout", 200, 200))
        self.assertEqual(result.verdict, "keep")
        self.assertIn("no canary-only difference", result.reasons[0])
        self.assertEqual(result.findings, [])

    def test_escalate_on_canary_5xx(self):
        result = analyze_rows(both("POST", "/checkout", 400, 500))
        self.assertEqual(result.verdict, "escalate")
        self.assertTrue(any("canary-only failure" in r for r in result.reasons))

    def test_no_escalate_when_both_5xx(self):
        result = analyze_rows(both("POST", "/checkout", 500, 500))
        self.assertEqual(result.verdict, "keep")
        self.assertTrue(any("pre-existing" in r for r in result.reasons))

    def test_escalate_on_latency(self):
        result = analyze_rows(both("GET", "/search", 200, 200, stable_latency=5,
                                  canary_latency=800, tier="high", repeats=2))
        self.assertEqual(result.verdict, "escalate")
        self.assertTrue(any("p95 latency" in r for r in result.reasons))

    def test_latency_needs_min_samples(self):
        result = analyze_rows(both("GET", "/search", 200, 200, stable_latency=5,
                                  canary_latency=800, tier="high"))
        self.assertEqual(result.verdict, "keep")

    def test_5xx_fires_on_a_high_tier_route(self):
        """Tier scales severity; it no longer decides whether a check runs."""
        result = analyze_rows(both("GET", "/search", 200, 500, tier="high"))
        self.assertEqual(result.verdict, "escalate")

    def test_regression_reasons_come_before_advisories(self):
        result = analyze_rows(
            both("POST", "/checkout", 500, 500)          # shared
            + both("POST", "/todos", 422, 500))          # canary-only
        self.assertEqual(result.verdict, "escalate")
        self.assertIn("canary-only failure", result.reasons[0])
        self.assertIn("pre-existing", result.reasons[1])

    def test_funnel_applies_window(self):
        rows = both("POST", "/checkout", 200, 500)
        rows = [row("stable", "POST", "/checkout", 200),
                row("canary", "POST", "/checkout", 500, 5, "2026-09-20T10:00:00+00:00")]
        self.assertEqual(decide_from_data(rows, CRIT, NOW).verdict, "keep")


class TestGrouping(unittest.TestCase):
    def test_six_cases_on_one_route_are_one_finding(self):
        rows = []
        for label in ("drop-required:title", "empty-string:title", "enum:priority",
                      "wrong-type:due_in_days", "bound-minimum:due_in_days", "happy-path"):
            rows += both("POST", "/todos", 422, 500, label=label)
        result = analyze_rows(rows, {"critical": ["/todos"], "high": []})
        self.assertEqual(len(result.reasons), 1, "one route, one sentence")
        self.assertIn("POST /todos 5xx on canary in 6/6 probes", result.reasons[0])
        self.assertIn("drop-required:title", result.reasons[0])
        self.assertIn("(+3 more)", result.reasons[0])

    def test_group_deltas_keeps_worst_kind_per_route(self):
        result = analyze_rows(both("POST", "/todos", 422, 500) + both("GET", "/todos", 200, 200))
        kinds = [g[0].kind for g in group_deltas(result.deltas)]
        self.assertEqual(kinds, [CANARY_ERROR])

    def test_describe_is_specific_per_kind(self):
        result = analyze_rows(both("POST", "/todos", 500, 500, tier="high")
                              + both("GET", "/todos", 200, 200, stable_latency=10,
                                     canary_latency=90, tier="high", repeats=2)
                              + both("GET", "/todos/1", 200, 500, tier="high"))
        by_kind = {}
        for group in group_deltas(result.deltas):
            by_kind.setdefault(group[0].kind, []).append(describe(group))
        self.assertIn("pre-existing, not a canary regression", by_kind[SHARED_ERROR][0])
        self.assertIn("+900%", by_kind[LATENCY_REGRESS][0])
        self.assertIn("canary-only failure", by_kind[CANARY_ERROR][0])


class TestRisk(unittest.TestCase):
    def test_risk_is_derived_not_constant(self):
        """The old generator hardcoded 0.1 for every finding."""
        total = analyze_rows(both("POST", "/todos", 422, 500, repeats=4))
        partial = analyze_rows(both("POST", "/todos", 422, 500, repeats=4)
                               + both("POST", "/todos", 200, 200, label="happy-path", repeats=4))
        self.assertGreater(risk_of(group_deltas(total.deltas)[0], 2.0), 0.5)
        self.assertLess(risk_of(group_deltas(partial.deltas)[0], 2.0),
                        risk_of(group_deltas(total.deltas)[0], 2.0))

    def test_critical_outranks_high_for_the_same_kind(self):
        crit = analyze_rows(both("POST", "/todos", 422, 500, tier="critical"))
        high = analyze_rows(both("GET", "/todos", 422, 500, tier="high"))
        self.assertGreater(risk_of(group_deltas(crit.deltas)[0], 2.0),
                           risk_of(group_deltas(high.deltas)[0], 2.0))

    def test_errors_outrank_latency(self):
        err = analyze_rows(both("POST", "/todos", 422, 500, repeats=3))
        lat = analyze_rows(both("GET", "/todos", 200, 200, stable_latency=5,
                                canary_latency=5000, tier="high", repeats=3))
        self.assertGreater(risk_of(group_deltas(err.deltas)[0], 2.0),
                           risk_of(group_deltas(lat.deltas)[0], 2.0))

    def test_risk_stays_in_range(self):
        result = analyze_rows(both("POST", "/todos", 422, 500, repeats=8))
        for group in group_deltas(result.deltas):
            self.assertLessEqual(risk_of(group, 2.0), 0.95)
            self.assertGreaterEqual(risk_of(group, 2.0), 0.0)


class TestProposals(unittest.TestCase):
    def _escalated(self, **kw):
        rows = both("POST", "/todos", 422, 500, repeats=3) + \
            both("GET", "/search", 200, 200, stable_latency=5, canary_latency=900,
                 tier="high", repeats=3)
        return build_proposals(analyze_rows(rows), **kw)

    def test_keep_yields_none(self):
        self.assertEqual(build_proposals(analyze_rows(both("POST", "/checkout", 200, 200))), [])

    def test_demo_headline_is_the_executable_flip(self):
        props = self._escalated()
        self.assertEqual(props[0]["action"], "traffic flip to stable")
        self.assertEqual(props[0]["execute"], {"target": "stable"})
        self.assertIn("proxy only", props[0]["blast_radius"])
        self.assertIn("instant", props[0]["reversibility"])

    def test_demo_carries_one_proposal_per_finding(self):
        props = self._escalated()
        self.assertEqual({p["kind"] for p in props},
                         {"flip", CANARY_ERROR, LATENCY_REGRESS})
        self.assertEqual([p["kind"] for p in props[1:]], [CANARY_ERROR, LATENCY_REGRESS])

    def test_ranked_worst_first_and_not_all_equal(self):
        props = self._escalated()
        risks = [p["risk"] for p in props]
        self.assertEqual(risks, sorted(risks, reverse=True))
        self.assertGreater(len(set(risks)), 1, "risks must be derived, not one constant")

    def test_only_the_flip_is_executable(self):
        props = self._escalated()
        self.assertEqual([p for p in props if p["execute"] is not None], [props[0]])

    def test_advisory_mode_has_nothing_executable(self):
        """External pairs: we have no traffic control, so nothing claims to."""
        props = self._escalated(advisory_only=True)
        self.assertTrue(all(p["execute"] is None for p in props))
        self.assertNotIn("flip", {p["kind"] for p in props})
        self.assertIn("hold traffic on stable", props[0]["action"])
        self.assertIn("advisory", props[0]["blast_radius"])
        self.assertIn("you control your traffic", props[0]["reversibility"])

    def test_evidence_cites_the_actual_rows(self):
        props = self._escalated()
        finding = next(p for p in props if p["kind"] == CANARY_ERROR)
        self.assertTrue(any("5xx on canary in 3/3" in e for e in finding["evidence"]))
        self.assertTrue(any("canary 500 vs stable 422" in e for e in finding["evidence"]))
        self.assertIn("POST /todos", finding["blast_radius"])

    def test_latency_only_headline_says_latency(self):
        rows = both("GET", "/search", 200, 200, stable_latency=5, canary_latency=900,
                    tier="high", repeats=3)
        props = build_proposals(analyze_rows(rows), advisory_only=True)
        self.assertIn("latency", props[0]["action"])

    def test_multi_route_headline_counts_routes(self):
        rows = both("POST", "/todos", 422, 500, repeats=2) + \
            both("PUT", "/todos/1", 422, 500, label="wrong-type:priority", repeats=2)
        props = build_proposals(analyze_rows(rows), advisory_only=True)
        self.assertIn("2 routes", props[0]["action"])

    def test_every_proposal_has_the_contract_fields(self):
        for p in self._escalated(advisory_only=True):
            for field in ("action", "risk", "blast_radius", "reversibility",
                          "execute", "kind", "tier", "evidence"):
                self.assertIn(field, p)
            self.assertTrue(p["action"])
            self.assertIsInstance(p["evidence"], list)
            self.assertTrue(p["evidence"])


class TestInformational(unittest.TestCase):
    def test_shared_errors_ride_along_without_being_regressions(self):
        result = analyze_rows(both("GET", "/todos", 500, 500, tier="high")
                              + both("POST", "/todos", 422, 500))
        props = informational_proposals(result)
        self.assertEqual([p["kind"] for p in props], [SHARED_ERROR])
        self.assertIsNone(props[0]["execute"])
        self.assertIn("pre-existing", props[0]["action"])

    def test_stable_only_failure_is_reported_not_escalated(self):
        result = analyze_rows(both("POST", "/todos", 500, 201))
        self.assertEqual(result.verdict, "keep")
        self.assertEqual([p["kind"] for p in informational_proposals(result)],
                         ["stable_error"])

    def test_nothing_to_report_when_healthy(self):
        self.assertEqual(informational_proposals(analyze_rows(both("GET", "/todos", 200, 200))), [])


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

    def test_advisory_set_is_structurally_unapprovable(self):
        """An advisory proposal set can never pass the gate — no `execute`."""
        rows = both("POST", "/todos", 422, 500, repeats=2)
        set_ = {"verdict": "escalate",
                "proposals": build_proposals(analyze_rows(rows), advisory_only=True)}
        self.assertIn("not in approved proposals", approve_execution(set_, "stable") or "")


def _jev_escalate(conf=0.9, regressing=(("post_checkout", 0.93),)):
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
        v, reasons = merge_verdict("escalate", ["canary 5xx on POST /checkout"], None)
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
        v, reasons = merge_verdict("keep", ["no canary-only difference"], _jev_escalate())
        self.assertEqual(v, "escalate")
        self.assertTrue(any("disagree" in r for r in reasons))

    def test_rules_only_signal_escalates_labeled(self):
        v, reasons = merge_verdict("escalate", ["r1"], _jev_keep())
        self.assertEqual(v, "escalate")
        self.assertTrue(any("disagree" in r for r in reasons))

    def test_agree_keep(self):
        v, reasons = merge_verdict("keep", ["no canary-only difference"], _jev_keep())
        self.assertEqual(v, "keep")

    def test_malformed_answers_default_keep(self):
        v, _ = merge_verdict("keep", ["no canary-only difference"], {"verdict": {"choice": "maybe"}})
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

    def test_summary_shows_the_paired_differences(self):
        deltas = analyze_rows(both("POST", "/todos", 422, 500)
                              + both("GET", "/todos", 200, 200, tier="high")).deltas
        summary = summarize_traffic(deltas)
        self.assertIn("POST /todos", summary)
        self.assertIn("canary_error", summary)
        self.assertIn("stable", summary)
        self.assertNotIn("GET /todos [", summary, "agreeing pairs are dropped")

    def test_summary_when_healthy(self):
        deltas = analyze_rows(both("GET", "/todos", 200, 200, tier="high")).deltas
        self.assertIn("Every paired probe", summarize_traffic(deltas))

    def test_questions_ask_about_the_paired_routes(self):
        deltas = analyze_rows(both("POST", "/todos", 422, 500)
                              + both("GET", "/todos", 200, 200, tier="high")).deltas
        q = build_questions({"critical": ["/todos"], "high": []}, deltas)
        self.assertEqual(q["verdict"]["type"], "choice")
        self.assertIn("post_todos_regressing", q)
        self.assertEqual(q["post_todos_regressing"]["type"], "noul")
        self.assertIn("[500]", q["post_todos_regressing"]["instructions"])
        # One question per route, not per case.
        self.assertNotIn("get_todos_regressing", q)

    def test_questions_fall_back_to_the_crit_map(self):
        q = build_questions(CRIT)
        self.assertIn("checkout_regressing", q)
        self.assertIn("search_regressing", q)


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
