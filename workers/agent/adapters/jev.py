"""Jev adapter: TypeSafe System One decision model over the traffic summary.

Jev is not a chat LLM — it takes a `state` string plus typed `questions`
(choice / noul) and returns calibrated answers. One request carries every
question (evaluated in parallel). Any failure — no key, timeout, bad shape —
returns None so the workflow falls back to rules alone. No exceptions escape.
"""
import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)
import httpx
from log_row import ServiceName, is_error  # noqa: E402

from config.settings import JEV_MODEL, TYPESAFE_API_BASE, TYPESAFE_API_KEY

_TIMEOUT_SECONDS = 10.0


def _path_of(endpoint: str) -> str:
    return endpoint.split("?", 1)[0]


def _qkey(endpoint: str) -> str:
    """Question keys must be plain identifiers: '/checkout' -> 'checkout'."""
    return "".join(c if c.isalnum() else "_" for c in _path_of(endpoint).strip("/")) or "root"


def summarize_traffic(rows: list[dict], crit: dict) -> str:
    """Compact per-endpoint stable/canary comparison for the Jev state string."""
    eps: list[str] = []
    for tier in ("critical", "high"):
        for ep in crit.get(tier, []):
            if ep not in eps:
                eps.append(ep)
    lines = []
    for ep in eps:
        parts = []
        for svc in (ServiceName.STABLE, ServiceName.CANARY):
            lat = sorted(
                r["latency_ms"] for r in rows
                if r["service"] == svc and _path_of(r["endpoint"]).startswith(ep)
            )
            errs = sum(
                1 for r in rows
                if r["service"] == svc and _path_of(r["endpoint"]).startswith(ep)
                and is_error(r["status_code"])
            )
            p95 = lat[max(0, int(len(lat) * 0.95) - 1)] if lat else -1
            parts.append(f"{svc} n={len(lat)} err={errs} p95={p95}ms")
        lines.append(f"{ep}: " + " | ".join(parts))
    return "Canary vs stable traffic summary. " + "; ".join(lines)


def build_questions(crit: dict) -> dict:
    """One verdict choice + one regression noul per endpoint, single request."""
    questions: dict = {
        "verdict": {
            "type": "choice",
            "instructions": "Given the canary vs stable comparison, what should the release operator do?",
            "criteria": {
                "escalate": "Canary is regressing vs stable: new errors or clear latency degradation. Needs human action.",
                "keep": "No meaningful difference between canary and stable. Safe to continue.",
            },
        }
    }
    for tier in ("critical", "high"):
        for ep in crit.get(tier, []):
            questions[f"{_qkey(ep)}_regressing"] = {
                "type": "noul",
                "instructions": f"Canary is regressing on {ep} relative to stable (errors or latency).",
            }
    return questions


def ask_jev(state: str, questions: dict) -> dict | None:
    """POST one System One evaluation. Returns the `answers` dict or None."""
    if not TYPESAFE_API_KEY or not questions:
        return None
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as c:
            r = c.post(
                f"{TYPESAFE_API_BASE}/v1/systemone",
                json={"model": JEV_MODEL, "state": state, "questions": questions},
                headers={"Authorization": f"Bearer {TYPESAFE_API_KEY}"},
            )
            r.raise_for_status()
            answers = r.json().get("answers")
            return answers if isinstance(answers, dict) else None
    except Exception:
        return None


def _choice_of(answers: dict) -> tuple[str, float]:
    v = answers.get("verdict") or {}
    choice = v.get("choice", "keep")
    try:
        conf = float(v.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return (choice if choice in ("escalate", "keep") else "keep", conf)


def merge_verdict(rules_verdict: str, rules_reasons: list[str], jev: dict | None) -> tuple[str, list[str]]:
    """Pure merge: escalate if EITHER source fires (human gate stays final).

    Execution always requires dashboard approval of a saved proposal set, so
    a Jev-only signal is safe to surface — it is labeled, never silent.
    """
    if jev is None:
        return rules_verdict, [*rules_reasons, "jev: unavailable (rules only)"]

    choice, conf = _choice_of(jev)
    jev_reasons = [f"jev: verdict={choice} (confidence {conf:.2f})"]
    for key, ans in jev.items():
        if key == "verdict" or not isinstance(ans, dict):
            continue
        ep = key.removesuffix("_regressing")
        try:
            p = float(ans.get("noul", 0.0))
        except (TypeError, ValueError):
            continue
        if p >= 0.5:
            jev_reasons.append(f"jev: /{ep} regressing on canary (p={p:.2f})")

    if rules_verdict == "escalate" or choice == "escalate":
        reasons = [f"rules: {r}" for r in rules_reasons] + jev_reasons
        if (rules_verdict == "escalate") != (choice == "escalate"):
            reasons.append(
                f"rules/jev disagree (rules={rules_verdict}, jev={choice}) — human review"
            )
        return "escalate", reasons
    return "keep", ["no critical diff", f"jev: keep (confidence {conf:.2f})"]
