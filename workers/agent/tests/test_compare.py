"""Tests for domain/compare.py — the stable/canary request pairing.

Run:  python3 -m unittest tests.test_compare -v   (from workers/agent/)
No Supabase, no HTTP, no mocks — the interface is the test surface.

The headline test is TestMaskingRegression: it reproduces a real bug from a
live external-target run, where one shared failure used to hide twelve
canary-only failures on the same path prefix.
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

from domain.compare import (  # noqa: E402
    CANARY_ERROR, LATENCY_REGRESS, OK, SHARED_ERROR, STABLE_ERROR,
    STATUS_DIVERGENCE, advisory, findings, pair_deltas, percentile, request_key,
    tier_of,
)

NOW = "2026-09-26T12:00:00+00:00"

CRIT = {"critical": ["/todos", "/todos/"], "high": ["/todos", "/todos/"]}


def row(service, method, path, status=200, latency=10, label="happy-path",
        tier="critical", source="synth", ts=NOW):
    """One probe row as the runner writes it (post-0007/0008 shape)."""
    return {
        "timestamp": ts, "service": service, "endpoint": path,
        "status_code": status, "latency_ms": latency,
        "case_method": method, "case_label": label,
        "case_tier": tier, "case_source": source,
    }


def pairs(rows):
    return pair_deltas(rows, CRIT)


def only(rows):
    deltas = pairs(rows)
    assert len(deltas) == 1, f"expected one delta, got {[d.route for d in deltas]}"
    return deltas[0]


class TestPairing(unittest.TestCase):
    def test_same_request_both_sides_is_one_delta(self):
        d = only([
            row("stable", "POST", "/todos", 201),
            row("canary", "POST", "/todos", 201),
        ])
        self.assertEqual(d.route, "POST /todos")
        self.assertEqual((d.n_stable, d.n_canary), (1, 1))
        self.assertEqual(d.kind, OK)

    def test_method_separates_buckets(self):
        """GET and DELETE on /todos are different requests."""
        deltas = pairs([
            row("stable", "GET", "/todos", 200),
            row("canary", "GET", "/todos", 200),
            row("stable", "DELETE", "/todos", 204),
            row("canary", "DELETE", "/todos", 500),
        ])
        by_route = {d.route: d for d in deltas}
        self.assertEqual(sorted(by_route), ["DELETE /todos", "GET /todos"])
        self.assertEqual(by_route["GET /todos"].kind, OK)
        self.assertEqual(by_route["DELETE /todos"].kind, CANARY_ERROR)

    def test_label_separates_cases_on_one_route(self):
        """Six failing bodies on POST /todos are six findings, not one bucket."""
        deltas = pairs([
            row("stable", "POST", "/todos", 422, label="drop-required:title"),
            row("canary", "POST", "/todos", 500, label="drop-required:title"),
            row("stable", "POST", "/todos", 422, label="empty-string:title"),
            row("canary", "POST", "/todos", 500, label="empty-string:title"),
        ])
        self.assertEqual(len(deltas), 2)
        self.assertTrue(all(d.kind == CANARY_ERROR for d in deltas))
        self.assertEqual(sorted(d.label for d in deltas),
                         ["drop-required:title", "empty-string:title"])

    def test_query_string_does_not_split_an_attributed_case(self):
        """A case label is the request identity; encoding noise must not fork it."""
        deltas = pairs([
            row("stable", "GET", "/todos?limit=1", 200, label="happy-path"),
            row("canary", "GET", "/todos?limit=1", 500, label="happy-path"),
        ])
        self.assertEqual(len(deltas), 1)
        self.assertEqual(deltas[0].path, "/todos")
        self.assertEqual(deltas[0].kind, CANARY_ERROR)

    def test_unattributed_rows_key_on_the_full_endpoint(self):
        """Demo rows (no label) keep distinct cases distinct."""
        rows = [
            {"timestamp": NOW, "service": s, "endpoint": "/search?q=normal",
             "status_code": 200, "latency_ms": 10}
            for s in ("stable", "canary")
        ] + [
            {"timestamp": NOW, "service": s, "endpoint": "/search?q=edge",
             "status_code": 200, "latency_ms": 10}
            for s in ("stable", "canary")
        ]
        self.assertEqual(len(pairs(rows)), 2)
        self.assertEqual(request_key(rows[0]), ("", "/search?q=normal", "/search?q=normal"))

    def test_proxy_rows_are_ignored(self):
        self.assertEqual(pairs([
            {"timestamp": NOW, "service": "proxy->stable", "endpoint": "/todos",
             "status_code": 200, "latency_ms": 5},
        ]), [])

    def test_repeats_aggregate_into_one_delta(self):
        d = only([row("stable", "POST", "/todos", 201) for _ in range(2)]
                 + [row("canary", "POST", "/todos", 500) for _ in range(2)])
        self.assertEqual((d.n_stable, d.n_canary), (2, 2))
        self.assertEqual(d.canary_errors, 2)
        self.assertEqual(d.hit_rate, 1.0)
        self.assertEqual(d.stable_errors, 0)


class TestMaskingRegression(unittest.TestCase):
    """A shared failure must never hide a canary-only one.

    Live bug: 12 canary-only 500s on POST /todos plus one 500 that BOTH sides
    returned on GET /todos?limit=<overflow>. The old rule bucketed by path
    prefix and required stable to be clean for the whole prefix, so the shared
    GET failure silenced every POST finding.
    """

    def _rows(self):
        rows = []
        # The canary-only failure: same request, 500 vs 422.
        for _ in range(12):
            rows.append(row("canary", "POST", "/todos", 500, label="drop-required:title"))
            rows.append(row("stable", "POST", "/todos", 422, label="drop-required:title"))
        # The shared failure: same request, 500 on BOTH sides.
        for _ in range(2):
            rows.append(row("canary", "GET", "/todos?limit=99999999999999999999",
                            500, label="wrong-type:limit", tier="high"))
            rows.append(row("stable", "GET", "/todos?limit=99999999999999999999",
                            500, label="wrong-type:limit", tier="high"))
        return rows

    def test_canary_only_failure_survives_a_shared_one(self):
        deltas = pairs(self._rows())
        by_kind = {}
        for d in deltas:
            by_kind.setdefault(d.kind, []).append(d)

        self.assertIn(CANARY_ERROR, by_kind, "canary-only 500s were masked")
        self.assertIn(SHARED_ERROR, by_kind, "the shared 500 should still be reported")

        canary_error = by_kind[CANARY_ERROR][0]
        self.assertEqual(canary_error.route, "POST /todos")
        self.assertEqual((canary_error.canary_errors, canary_error.n_canary), (12, 12))
        self.assertEqual(canary_error.stable_errors, 0)

    def test_only_the_canary_only_failure_is_a_regression(self):
        deltas = pairs(self._rows())
        self.assertEqual([d.route for d in findings(deltas)], ["POST /todos"])
        self.assertEqual([d.route for d in advisory(deltas)], ["GET /todos"])

    def test_shared_failure_alone_does_not_escalate(self):
        rows = [row("canary", "GET", "/todos", 500), row("stable", "GET", "/todos", 500)]
        self.assertEqual(only(rows).kind, SHARED_ERROR)
        self.assertEqual(findings(pairs(rows)), [])


class TestClassification(unittest.TestCase):
    def test_stable_only_error_is_not_a_regression(self):
        d = only([row("stable", "POST", "/todos", 500), row("canary", "POST", "/todos", 201)])
        self.assertEqual(d.kind, STABLE_ERROR)
        self.assertFalse(d.is_regression)

    def test_status_divergence_without_5xx(self):
        d = only([row("stable", "POST", "/todos", 201), row("canary", "POST", "/todos", 200)])
        self.assertEqual(d.kind, STATUS_DIVERGENCE)
        self.assertFalse(d.is_regression)

    def test_latency_needs_min_samples_per_side(self):
        one = pairs([row("stable", "GET", "/todos", 200, 10, tier="high"),
                     row("canary", "GET", "/todos", 200, 900, tier="high")])
        self.assertEqual(one[0].kind, OK, "one sample per side is noise, not latency")

        two = pairs([row("stable", "GET", "/todos", 200, 10, tier="high") for _ in range(2)]
                    + [row("canary", "GET", "/todos", 200, 900, tier="high") for _ in range(2)])
        self.assertEqual(two[0].kind, LATENCY_REGRESS)

    def test_latency_under_the_factor_is_agreement(self):
        d = only([row("stable", "GET", "/todos", 200, 100, tier="high") for _ in range(2)]
                 + [row("canary", "GET", "/todos", 200, 150, tier="high") for _ in range(2)])
        self.assertEqual(d.kind, OK)
        self.assertEqual(d.latency_ratio, 1.5)

    def test_error_outranks_latency(self):
        d = only([row("stable", "GET", "/todos", 200, 10, tier="high") for _ in range(2)]
                 + [row("canary", "GET", "/todos", 500, 900, tier="high") for _ in range(2)])
        self.assertEqual(d.kind, CANARY_ERROR)
        self.assertEqual(d.latency_ratio, 90.0, "latency is still recorded, just not the kind")

    def test_worst_first_ordering(self):
        deltas = pairs([
            row("stable", "GET", "/todos", 200, 10, tier="high"),
            row("canary", "GET", "/todos", 200, 10, tier="high"),
            row("stable", "POST", "/todos", 500),
            row("canary", "POST", "/todos", 500),
            row("stable", "PUT", "/todos/1", 200),
            row("canary", "PUT", "/todos/1", 500),
        ])
        self.assertEqual([d.kind for d in deltas],
                         [CANARY_ERROR, SHARED_ERROR, OK])

    def test_tier_comes_from_the_row_then_the_crit_map(self):
        self.assertEqual(only([row("stable", "PUT", "/todos/1", 200, tier="critical"),
                               row("canary", "PUT", "/todos/1", 500, tier="critical")]).tier,
                         "critical")
        untiered = [
            {"timestamp": NOW, "service": s, "endpoint": "/todos", "case_method": "POST",
             "status_code": st, "latency_ms": 5, "case_tier": None, "case_source": None,
             "case_label": "x"}
            for s, st in (("stable", 200), ("canary", 500))
        ]
        self.assertEqual(only(untiered).tier, "critical")

    def test_hit_rate_and_serialisation(self):
        d = only([row("stable", "POST", "/todos", 422) for _ in range(4)]
                 + [row("canary", "POST", "/todos", 500) for _ in range(4)])
        self.assertEqual(d.hit_rate, 1.0)
        payload = d.to_dict()
        self.assertEqual(payload["kind"], CANARY_ERROR)
        self.assertEqual(payload["canary_statuses"], [500, 500, 500, 500])
        self.assertEqual(payload["method"], "POST")

    def test_tier_of_falls_back_to_high(self):
        self.assertEqual(tier_of(CRIT, "/checkout"), "high")
        self.assertEqual(tier_of(CRIT, "/todos"), "critical")

    def test_percentile_clamps(self):
        self.assertEqual(percentile([5], 0.95), 5)
        self.assertEqual(percentile([1, 2, 3], 0.95), 3)
        with self.assertRaises(ValueError):
            percentile([], 0.95)


if __name__ == "__main__":
    unittest.main()
