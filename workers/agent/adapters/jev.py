"""Jev adapter: TypeSafe System One decision model over the traffic summary.

Jev is not a chat LLM — it takes a `state` string plus typed `questions`
(choice / noul) and returns calibrated answers. One request carries every
question (evaluated in parallel). Any failure — no key, timeout, bad shape —
returns None so the workflow falls back to rules alone. No exceptions escape.

The `state` it judges is the paired probe table from domain/compare.py: the
same request, its response on each side, and what the pairing concluded.
"""
import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)
import httpx

from config.settings import JEV_MODEL, TYPESAFE_API_BASE, TYPESAFE_API_KEY

_TIMEOUT_SECONDS = 10.0


def _path_of(endpoint: str) -> str:
    return endpoint.split("?", 1)[0]


def _qkey(endpoint: str) -> str:
    """Question keys must be plain identifiers: '/checkout' -> 'checkout'."""
    return "".join(c if c.isalnum() else "_" for c in _path_of(endpoint).strip("/")) or "root"


def _dkey(delta) -> str:
    """Question key for one request pair: method + path, 'POST /todos' -> post_todos."""
    path = "_".join(p for p in _path_of(delta.path).split("/") if p)
    key = "_".join(f"{delta.method}_{path}".lower().split()).replace("-", "_")
    return key.replace("/", "_") or "root"


def summarize_traffic(deltas: list, limit: int = 12) -> str:
    """The paired request table Jev reasons over — worst pairs first.

    Jev is a decision model, not a summarizer: it needs the evidence the
    pairing produced (same request, both responses), not per-endpoint
    aggregates. Pairs that agree are dropped so its attention goes to the
    differences, which is what a verdict question is about.
    """
    lines = []
    for d in deltas[:limit]:
        if d.kind == "ok":
            continue
        lines.append(
            f"{d.route} [{d.tier}/{d.source or 'unknown'}] "
            f"canary n={d.n_canary} statuses={list(d.canary_statuses)} p95={d.p95_canary}ms | "
            f"stable n={d.n_stable} statuses={list(d.stable_statuses)} p95={d.p95_stable}ms | "
            f"difference={d.kind}"
        )
    if not lines:
        return ("Canary vs stable traffic summary. Every paired probe returned the same "
                "status class on both versions at comparable latency.")
    return ("Canary vs stable traffic summary (paired probes, worst first). "
            + "; ".join(lines))


def build_questions(crit: dict, deltas: list | None = None) -> dict:
    """One verdict choice + one regression noul per distinct route, one request.

    Routes come from the paired deltas when they're available — that's what
    the summary describes. Falls back to the criticality map when it isn't.
    """
    questions: dict = {
        "verdict": {
            "type": "choice",
            "instructions": (
                "Given the paired canary-vs-stable probe results, what should the "
                "release operator do?"
            ),
            "criteria": {
                "escalate": "Canary is regressing vs stable: new errors or clear latency degradation. Needs human action.",
                "keep": "No meaningful difference between canary and stable. Safe to continue.",
            },
        }
    }
    if deltas is None:
        for tier in ("critical", "high"):
            for ep in crit.get(tier, []):
                questions[f"{_qkey(ep)}_regressing"] = {
                    "type": "noul",
                    "instructions": f"Canary is regressing on {ep} relative to stable (errors or latency).",
                }
        return questions
    seen: set[str] = set()
    for d in deltas:
        if d.kind == "ok":
            continue  # ask about differences only, not agreements
        key = _dkey(d)
        if key in seen:
            continue
        seen.add(key)
        questions[f"{key}_regressing"] = {
            "type": "noul",
            "instructions": (
                f"Canary is regressing on {d.method} {d.path} relative to stable "
                f"(same request, different outcome: {list(d.canary_statuses)} vs "
                f"{list(d.stable_statuses)})."
            ),
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
        ep = key.removesuffix("_regressing").replace("_", " ")
        try:
            p = float(ans.get("noul", 0.0))
        except (TypeError, ValueError):
            continue
        if p >= 0.5:
            jev_reasons.append(f"jev: {ep} regressing on canary (p={p:.2f})")

    if rules_verdict == "escalate" or choice == "escalate":
        reasons = [f"rules: {r}" for r in rules_reasons] + jev_reasons
        if (rules_verdict == "escalate") != (choice == "escalate"):
            reasons.append(
                f"rules/jev disagree (rules={rules_verdict}, jev={choice}) — human review"
            )
        return "escalate", reasons
    return "keep", ["no critical diff", f"jev: keep (confidence {conf:.2f})"]
