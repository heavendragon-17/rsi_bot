"""
Export OpenAPI schema from FastAPI and generate TypeScript types.

Usage:
    python -m app.api.export_schema
    python scripts/gen_ts_types.py

Outputs:
    ui/src/types/openapi.json   (full OpenAPI spec — for reference / tooling)
    ui/src/types/generated.ts   (TypeScript interfaces — never edit manually)
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger()


# Models to include in generated TS (filters out FastAPI internals
# like HTTPValidationError / ValidationError).
_INCLUDE = {
    "BacktestMode",
    "BacktestRequest",
    "BacktestStartResponse",
    "RunSummary",
    "RunDetail",
    "TimeseriesResponse",
    "HistoryResponse",
    "DataStatusResponse",
    "DownloadStartResponse",
    "StrategyInfo",
}


# ---------------------------------------------------------------------------
# JSON Schema → TypeScript converter
# ---------------------------------------------------------------------------


def _ts_type(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    """Recursively convert a JSON Schema node to a TypeScript type string."""
    # $ref  →  look up in defs (works for both #/$defs/X and #/components/schemas/X)
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        # Named type (enum or interface in _INCLUDE) → use the name directly
        if ref_name in _INCLUDE:
            return ref_name
        ref_schema = defs.get(ref_name, {})
        return _ts_type(ref_schema, defs) if ref_name in defs else "unknown"

    # anyOf / oneOf  →  union  (handles `str | None` pattern from Pydantic)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            parts = [_ts_type(s, defs) for s in schema[key]]
            unique: list[str] = list(dict.fromkeys(parts))
            return " | ".join(unique)

    # Enum literals (inline)
    if "enum" in schema:
        return " | ".join(f'"{v}"' for v in schema["enum"])

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
        inner = _ts_type(items, defs)
        # Wrap union types in parens for array: (A | B)[]
        return f"({inner})[]" if " | " in inner else f"{inner}[]"

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


def _render_enum(name: str, schema: dict[str, Any]) -> str:
    """Render a TypeScript string union type from an enum schema."""
    values = schema["enum"]
    union = " | ".join(f'"{v}"' for v in values)
    return f"export type {name} = {union};"


def _render_interface(name: str, schema: dict[str, Any], defs: dict[str, Any]) -> str:
    """Render a TypeScript interface from an object schema."""
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
# Public API
# ---------------------------------------------------------------------------


def export_openapi_and_ts(out_dir: str) -> None:
    """Export OpenAPI JSON and generated TypeScript to *out_dir*."""
    from app.api.main import app

    spec = app.openapi()
    all_schemas = spec.get("components", {}).get("schemas", {})

    os.makedirs(out_dir, exist_ok=True)

    # ── openapi.json ──────────────────────────────────────────────────────
    openapi_path = os.path.join(out_dir, "openapi.json")
    with open(openapi_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    logger.info("file_written", path=openapi_path)

    # ── generated.ts ──────────────────────────────────────────────────────
    # Partition into enums and interfaces, keeping only _INCLUDE models
    enums: list[str] = []
    interfaces: list[str] = []

    for name in _INCLUDE:
        schema = all_schemas.get(name)
        if schema is None:
            continue
        if "enum" in schema:
            enums.append(_render_enum(name, schema))
        else:
            interfaces.append(_render_interface(name, schema, all_schemas))

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = (
        "/* AUTO-GENERATED — do not edit manually.\n"
        " * Source: Pydantic models in app/api/schemas.py\n"
        " * Run `python scripts/gen_ts_types.py` to regenerate.\n"
        f" * Generated: {now}\n"
        " */\n"
    )
    body = "\n\n".join(enums + interfaces)
    ts_path = os.path.join(out_dir, "generated.ts")
    with open(ts_path, "w", encoding="utf-8") as f:
        f.write(header + "\n" + body + "\n")
    logger.info("file_written", path=ts_path)


def main() -> None:
    out_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "ui", "src", "types"))
    export_openapi_and_ts(out_dir)


if __name__ == "__main__":
    main()
