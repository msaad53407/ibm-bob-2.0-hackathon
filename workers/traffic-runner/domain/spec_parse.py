"""OpenAPI 3.x parsing: spec text → endpoint inventory. No LLM, no network.

Output per operation:
  {method, path_template, params: [{in, name, required, schema}],
   body_schema | None}
$refs resolve locally (depth-limited, cycle-safe). Anything else —
OpenAPI 2.x, remote refs, unparseable text — raises SpecError with a
human-readable reason the dashboard shows verbatim.
"""
import json

import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)

try:
    import yaml
except ImportError:  # pragma: no cover — Dockerfile always installs pyyaml
    yaml = None


class SpecError(ValueError):
    """Raised when the pasted spec cannot become an inventory."""


_REF_DEPTH_LIMIT = 10


def _load(text: str) -> dict:
    try:
        if yaml is not None:
            doc = yaml.safe_load(text)
        else:
            doc = json.loads(text)
    except Exception as exc:
        raise SpecError(f"spec is not valid YAML/JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise SpecError("spec must be a YAML/JSON object")
    return doc


def _resolve(node, root: dict, depth: int = 0):
    """Resolve local '#/...' $refs; leave remote refs unresolved (error later)."""
    if depth > _REF_DEPTH_LIMIT:
        raise SpecError("spec has excessively nested $refs (possible cycle)")
    if isinstance(node, dict):
        if set(node.keys()) == {"$ref"}:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise SpecError(f"only local $refs supported, got: {ref!r}")
            cur = root
            for part in ref[2:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(cur, dict) or part not in cur:
                    raise SpecError(f"$ref target missing: {ref!r}")
                cur = cur[part]
            return _resolve(cur, root, depth + 1)
        return {k: _resolve(v, root, depth) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(v, root, depth) for v in node]
    return node


def example_for(schema: dict):
    """Best-effort example value for a JSON schema (used to fill params)."""
    if not isinstance(schema, dict):
        return "1"
    for key in ("example", "default"):
        if key in schema:
            return schema[key]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "integer":
        return schema.get("minimum", 1)
    if t == "number":
        return schema.get("minimum", 1.0)
    if t == "boolean":
        return True
    if t == "array":
        return [example_for(schema.get("items", {}))]
    if t == "object" or "properties" in schema:
        return {k: example_for(v) for k, v in schema.get("properties", {}).items()}
    return "1"


def parse_spec(text: str) -> dict:
    """Parse spec text → {version, operations}. Raises SpecError."""
    if not text or not text.strip():
        raise SpecError("spec is empty — paste OpenAPI YAML or JSON")
    doc = _resolve(_load(text), _load(text))
    version = str(doc.get("openapi", ""))
    if not version.startswith("3."):
        raise SpecError(
            f"only OpenAPI 3.x supported, got: {version or 'missing version'!r}"
        )
    paths = doc.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise SpecError("spec has no paths to probe")
    operations = []
    for path_template, item in paths.items():
        if not isinstance(item, dict):
            continue
        shared_params = item.get("parameters", []) or []
        for method, op in item.items():
            if method.lower() not in (
                "get", "post", "put", "patch", "delete", "head", "options",
            ):
                continue
            if not isinstance(op, dict):
                continue
            params = []
            for p in (shared_params + (op.get("parameters", []) or [])):
                if not isinstance(p, dict):
                    continue
                params.append({
                    "in": p.get("in", "query"),
                    "name": p.get("name", ""),
                    "required": bool(p.get("required", p.get("in") == "path")),
                    "schema": p.get("schema", {}) or {},
                })
            body_schema = None
            body = op.get("requestBody") or {}
            content = (body.get("content") or {}) if isinstance(body, dict) else {}
            for ctype in ("application/json",):
                if ctype in content:
                    body_schema = (content[ctype].get("schema") or {}) or None
                    break
            operations.append({
                "method": method.upper(),
                "path_template": path_template,
                "params": [p for p in params if p["name"]],
                "body_schema": body_schema,
            })
    if not operations:
        raise SpecError("no probeable operations found under paths")
    return {"version": version, "operations": operations}


def fill_path(template: str, params: list[dict], values: dict | None = None) -> str:
    """Substitute {path} params: explicit values win, else schema examples."""
    values = values or {}
    out = template
    for p in params:
        if p["in"] != "path":
            continue
        val = values.get(p["name"], example_for(p.get("schema", {})))
        out = out.replace("{" + p["name"] + "}", str(val))
    return out


def query_string(params: list[dict], values: dict | None = None) -> str:
    """Build '?a=b&…' from query params present in values (required first).

    Params absent from values are OMITTED (expresses dropped params),
    never backfilled — callers pass examples explicitly for the happy path.
    """
    values = values or {}
    parts = []
    for p in sorted(params, key=lambda p: not p["required"]):
        if p["in"] != "query" or p["name"] not in values:
            continue
        parts.append(f"{p['name']}={values[p['name']]}")
    return ("?" + "&".join(parts)) if parts else ""
