"""Deterministic edge-case synthesis: operations → runnable probe cases.

No LLM, no network — pure functions over the spec inventory. Each case:
  {method, path, body, tier, source: "synth", label}
`label` is the case's identity ('happy-path', 'drop-required:title', …); the
runner stamps it onto every log row the case produces so the Decision can
pair the stable/canary response to the same request and cite the case that
found it. Mutating methods default to critical tier (a 5xx there is a
regression); reads default to high (latency-sensitive). Caps keep runs bounded.
"""
import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)

from domain.spec_parse import example_for, fill_path, query_string
from verification import tier_for_method

MAX_CASES_PER_OP = 8
MAX_TOTAL_CASES = 40

_WRONG_TYPE = {str: 12345, int: "not-a-number", float: "not-a-number",
               bool: "maybe", list: {}, dict: []}


def _props(schema: dict) -> dict:
    return (schema.get("properties") or {}) if isinstance(schema, dict) else {}


def _required(schema: dict) -> list[str]:
    req = (schema.get("required") or []) if isinstance(schema, dict) else []
    return [r for r in req if isinstance(r, str)]


def _wrong_value(value):
    if isinstance(value, bool):
        return "maybe"
    if isinstance(value, int):
        return "not-a-number"
    if isinstance(value, float):
        return "not-a-number"
    if isinstance(value, str):
        return 12345
    if isinstance(value, list):
        return {}
    if isinstance(value, dict):
        return []
    return None


def _param_overrides(params: list[dict], skip: str | None = None,
                     wrong: str | None = None) -> dict:
    """Explicit path/query values: drop `skip`, mistype `wrong`, else examples."""
    values: dict = {}
    for p in params:
        if p["name"] == skip:
            continue
        if p["name"] == wrong:
            values[p["name"]] = _wrong_value(example_for(p.get("schema", {})))
        else:
            values[p["name"]] = example_for(p.get("schema", {}))
    return values


def _render(op: dict, values: dict) -> tuple[str, dict | None]:
    path = fill_path(op["path_template"], op["params"], values)
    qs = query_string(op["params"], values)
    body = None
    if op["body_schema"] is not None:
        body = values.get("__body__", example_for(op["body_schema"]))
    return path + qs, body


def synthesize(operations: list[dict]) -> list[dict]:
    """Build capped edge-case list for parsed operations."""
    tier_of = lambda op: tier_for_method(op["method"])
    cases: list[dict] = []
    for op in operations:
        tier = tier_of(op)
        op_cases: list[dict] = []

        def add(path, body, label):
            if len(op_cases) < MAX_CASES_PER_OP:
                op_cases.append({"method": op["method"], "path": path,
                                 "body": body, "tier": tier, "source": "synth",
                                 "label": label})

        # 1. Happy path: examples everywhere.
        base = _param_overrides(op["params"])
        if op["body_schema"] is not None:
            base["__body__"] = example_for(op["body_schema"])
        path, body = _render(op, base)
        add(path, body, "happy-path")

        # 2. Drop each required query param / body prop.
        for p in op["params"]:
            if p["in"] == "query" and p["required"]:
                v = _param_overrides(op["params"], skip=p["name"])
                if op["body_schema"] is not None:
                    v["__body__"] = example_for(op["body_schema"])
                add(*_render(op, v), f"drop-required:{p['name']}")
        for name in _required(op["body_schema"] or {}):
            full = example_for(op["body_schema"])
            if isinstance(full, dict) and name in full:
                v = dict(base)
                v["__body__"] = {k: val for k, val in full.items() if k != name}
                add(*_render(op, v), f"drop-required:{name}")

        # 3. Wrong-type each query param / body prop.
        for p in op["params"]:
            if p["in"] == "query":
                v = _param_overrides(op["params"], wrong=p["name"])
                if op["body_schema"] is not None:
                    v["__body__"] = example_for(op["body_schema"])
                add(*_render(op, v), f"wrong-type:{p['name']}")
        full = example_for(op["body_schema"]) if op["body_schema"] else None
        if isinstance(full, dict):
            for name, val in full.items():
                w = _wrong_value(val)
                if w is None:
                    continue
                v = dict(base)
                v["__body__"] = {**full, name: w}
                add(*_render(op, v), f"wrong-type:{name}")
                # 4. Empty-string each string prop.
                if isinstance(val, str):
                    v2 = dict(base)
                    v2["__body__"] = {**full, name: ""}
                    add(*_render(op, v2), f"empty-string:{name}")

        # 5. Enum violation + numeric boundaries from the schema.
        for name, subschema in _props(op["body_schema"] or {}).items():
            if not isinstance(subschema, dict):
                continue
            if subschema.get("enum"):
                v = dict(base)
                v["__body__"] = {**full, name: "invalid-enum-value"} if isinstance(full, dict) else full
                add(*_render(op, v), f"enum:{name}")
            for bound, delta in (("minimum", -1), ("maximum", 1)):
                if bound in subschema and isinstance(full, dict):
                    v = dict(base)
                    v["__body__"] = {**full, name: subschema[bound] + delta}
                    add(*_render(op, v), f"bound-{bound}:{name}")

        cases.extend(op_cases)
        if len(cases) >= MAX_TOTAL_CASES:
            break
    return cases[:MAX_TOTAL_CASES]
