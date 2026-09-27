"""LLM case enhancement: OpenRouter (default DeepSeek flash) proposes
adversarial-but-plausible inputs per endpoint. Strictly an upgrade over the
deterministic synthesizer — every case is validated against the inventory,
and any failure (no key, timeout, bad JSON) returns [] so registration
falls back to synth-only. No exceptions escape.
"""
import json

import httpx

_TIMEOUT_DEFAULT = 60.0
_MAX_LLM_CASES = 10

_SYSTEM = (
    "You generate adversarial API test inputs. Given endpoint descriptions, "
    "return ONLY JSON: {\"cases\": [{\"method\": \"GET|POST|...\", "
    "\"path\": \"/filled/path?query=1\", \"body\": {...} or null, "
    "\"tier\": \"critical|high\", \"why\": \"one line\"}]}. "
    "Rules: use only the listed method+path combos; fill all {path} params "
    "with plausible values; prefer inputs a real client could send that "
    "might break a buggy server (missing fields, wrong types, empty "
    "strings, extremes, unknown enum values). At most 4 cases per endpoint."
)


def _inventory_text(operations: list[dict]) -> str:
    lines = []
    for op in operations:
        params = ", ".join(
            f"{p['in']}:{p['name']}{'*' if p['required'] else ''}"
            f"<{(p.get('schema') or {}).get('type', '?')}>"
            for p in op["params"]
        )
        body = ""
        if op["body_schema"]:
            props = (op["body_schema"].get("properties") or {}) if isinstance(op["body_schema"], dict) else {}
            req = (op["body_schema"].get("required") or []) if isinstance(op["body_schema"], dict) else []
            body = " body={" + ", ".join(
                f"{k}{'*' if k in req else ''}<{(v or {}).get('type', '?')}>"
                for k, v in props.items()) + "}"
        lines.append(f"{op['method']} {op['path_template']} [{params}]{body}")
    return "\n".join(lines)


def _template_match(path: str, template: str) -> bool:
    """Filled path matches its template: compare segment-wise, {x} = wildcard."""
    import re
    pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", template.split("?")[0]) + "$"
    return re.match(pattern, path.split("?")[0]) is not None


def _label(case: dict) -> str:
    """Short, stable case identity: the model's one-line `why`, else a shape tag.

    Labels land on every log row the case produces and are quoted in proposal
    evidence, so they must be single-line and bounded.
    """
    why = str(case.get("why") or "").strip().splitlines()
    text = why[0].strip() if why else ""
    if not text:
        return "llm-case"
    return text[:80]


def _valid(case: dict, operations: list[dict]) -> dict | None:
    """Keep the case only if method+path match a known operation."""
    if not isinstance(case, dict):
        return None
    method = str(case.get("method", "")).upper()
    path = str(case.get("path", ""))
    tier = case.get("tier") if case.get("tier") in ("critical", "high") else None
    body = case.get("body")
    if not method or not path.startswith("/"):
        return None
    match = next((op for op in operations
                  if op["method"] == method and _template_match(path, op["path_template"])), None)
    if match is None:
        return None
    if body is not None:
        try:
            json.dumps(body)
        except (TypeError, ValueError):
            return None
    return {"method": method, "path": path, "body": body,
            "tier": tier or ("critical" if method in ("POST", "PUT", "PATCH", "DELETE") else "high"),
            "source": "llm", "label": _label(case)}


def enhance_with_llm(operations: list[dict], *, api_key: str, model: str,
                     base: str = "https://openrouter.ai/api/v1",
                     timeout: float = _TIMEOUT_DEFAULT) -> list[dict]:
    """Ask the LLM for extra edge cases. Returns validated cases or []."""
    if not api_key or not operations:
        return []
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(
                f"{base.rstrip('/')}/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": "Endpoints:\n" + _inventory_text(operations)},
                    ],
                    "response_format": {"type": "json_object"},
                },
                headers={"Authorization": f"Bearer {api_key}",
                         "X-Title": "GuardRail canary verifier"},
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        raw = data.get("cases") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            return []
        out = []
        for case in raw:
            v = _valid(case, operations)
            if v is not None:
                out.append(v)
            if len(out) >= _MAX_LLM_CASES:
                break
        return out
    except Exception:
        return []
