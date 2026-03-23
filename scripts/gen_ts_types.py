"""
Auto-generate TypeScript types from FastAPI OpenAPI schema.

Reads Pydantic models via the FastAPI app's OpenAPI spec and writes:
    ui/src/types/openapi.json   — full OpenAPI spec (for reference / tooling)
    ui/src/types/generated.ts   — TypeScript interfaces (never edit manually)

Usage:
    python scripts/gen_ts_types.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.export_schema import export_openapi_and_ts


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "ui" / "src" / "types"
    export_openapi_and_ts(str(out_dir))


if __name__ == "__main__":
    main()
