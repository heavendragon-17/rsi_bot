"""
Export Pydantic schemas as JSON Schema + TypeScript types.

Usage:
    python app/api/export_schema.py

Outputs:
    ui/src/types/api-schema.json  (JSON Schema — for reference / future tooling)
    ui/src/types/api-types.ts     (TypeScript interfaces — never edit manually)
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# JSON Schema → TypeScript converter
# ---------------------------------------------------------------------------

def _ts_type(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    """Recursively convert a JSON Schema node to a TypeScript type string."""
    # $ref  →  look up in $defs
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        return _ts_type(defs.get(ref_name, {}), defs) if ref_name in defs else "unknown"

    # anyOf / oneOf  →  union  (handles `str | None` pattern from Pydantic)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            parts = [_ts_type(s, defs) for s in schema[key]]
            unique: list[str] = list(dict.fromkeys(parts))
            return " | ".join(unique)

    t = schema.get("type")
    if t == "string":
        return "string"
    if t in ("integer", "number"):
        return "number"
    if t == "boolean":
        return "boolean"
    if t == "null":
        return "null"

    if t == "array":
        items = schema.get("items", {})
        return f"{_ts_type(items, defs)}[]"

    if t == "object":
        props = schema.get("properties")
        if props:
            required = set(schema.get("required", []))
            fields = []
            for name, prop_schema in props.items():
                opt = "" if name in required else "?"
                fields.append(f"    {name}{opt}: {_ts_type(prop_schema, defs)};")
            return "{\n" + "\n".join(fields) + "\n  }"
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"Record<string, {_ts_type(additional, defs)}>"
        return "Record<string, unknown>"

    return "unknown"


def _interface(name: str, schema: dict[str, Any]) -> str:
    """Render a single TypeScript interface from a Pydantic model JSON Schema."""
    defs = schema.get("$defs", {})
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    lines = [f"export interface {name} {{"]
    for field_name, field_schema in properties.items():
        optional = "" if field_name in required_fields else "?"
        ts_t = _ts_type(field_schema, defs)
        lines.append(f"  {field_name}{optional}: {ts_t};")
    lines.append("}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    from app.api.schemas import (
        BacktestRequest,
        BacktestStartResponse,
        DataStatusResponse,
        DownloadStartResponse,
        HistoryResponse,
        RunDetail,
        RunSummary,
        StrategyInfo,
        TimeseriesResponse,
    )

    MODELS: dict[str, type] = {
        "BacktestRequest": BacktestRequest,
        "BacktestStartResponse": BacktestStartResponse,
        "RunSummary": RunSummary,
        "RunDetail": RunDetail,
        "TimeseriesResponse": TimeseriesResponse,
        "HistoryResponse": HistoryResponse,
        "DataStatusResponse": DataStatusResponse,
        "DownloadStartResponse": DownloadStartResponse,
        "StrategyInfo": StrategyInfo,
    }

    schemas = {name: model.model_json_schema() for name, model in MODELS.items()}

    out_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "ui", "src", "types")
    )
    os.makedirs(out_dir, exist_ok=True)

    # ── api-schema.json ───────────────────────────────────────────────────
    schema_path = os.path.join(out_dir, "api-schema.json")
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schemas, f, indent=2)
    print(f"Written: {schema_path}")

    # ── api-types.ts ──────────────────────────────────────────────────────
    ts_path = os.path.join(out_dir, "api-types.ts")
    header = (
        "/* AUTO-GENERATED — do not edit manually.\n"
        " * Run `npm run generate-types` to regenerate.\n"
        f" * Generated: {datetime.utcnow().isoformat()}Z\n"
        " */\n\n"
    )
    body = "\n\n".join(_interface(name, schema) for name, schema in schemas.items())
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(header + body + "\n")
    print(f"Written: {ts_path}")


if __name__ == "__main__":
    main()
