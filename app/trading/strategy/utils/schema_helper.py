"""
Schema generation for strategy config dataclasses.

Provides SchemaConfigMixin (adds param_schema() classmethod) and
generate_schema_from_dataclass() for auto-generating JSON Schema
with UI metadata from frozen dataclass fields.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any, get_type_hints

# Python type → JSON Schema type mapping
_TYPE_MAP = {
    int: "integer",
    float: "number",
    bool: "boolean",
    str: "string",
}


class SchemaConfigMixin:
    """Mixin that adds param_schema() to any frozen dataclass with METADATA/UI_GROUPS.

    Usage::

        @dataclass(frozen=True)
        class MyConfig(SchemaConfigMixin):
            METADATA = MY_METADATA
            UI_GROUPS = MY_GROUPS
            field1: int = 10
    """

    METADATA: dict[str, dict[str, Any]] = {}
    UI_GROUPS: dict[str, dict[str, Any]] = {}

    @classmethod
    def param_schema(cls) -> dict:
        """Returns JSON Schema with UI metadata for dynamic form generation."""
        return generate_schema_from_dataclass(cls, cls.METADATA, cls.UI_GROUPS)


def generate_schema_from_dataclass(
    cls,
    metadata: dict[str, dict[str, Any]] | None = None,
    ui_groups: dict[str, dict[str, Any]] | None = None,
) -> dict:
    """Auto-generate JSON Schema from frozen dataclass fields + metadata.

    1. Introspects dataclass fields for name, type, default
    2. Merges UI metadata (title, min/max, group, etc.) from metadata dict
    3. Attaches ui_groups for frontend collapsible sections
    """
    hints = get_type_hints(cls)
    meta = metadata or {}
    properties: dict[str, Any] = {}

    for field in dataclasses.fields(cls):
        # Skip non-serializable class vars
        if field.name in ("METADATA", "UI_GROUPS"):
            continue

        field_type = hints.get(field.name, str)
        prop: dict[str, Any] = {
            "title": field.name.replace("_", " ").title(),
            "type": _TYPE_MAP.get(field_type, "string"),
        }

        # Extract default value
        if field.default is not dataclasses.MISSING:
            prop["default"] = field.default
        elif field.default_factory is not dataclasses.MISSING:
            val = field.default_factory()
            if isinstance(val, (dict, list)):
                val = copy.deepcopy(val)
            prop["default"] = val

        # Merge UI metadata overrides (title, min, max, group, etc.)
        if field.name in meta:
            prop.update(meta[field.name])

        properties[field.name] = prop

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if ui_groups:
        schema["ui_groups"] = ui_groups

    return schema
