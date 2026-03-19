#!/usr/bin/env python3
"""
Architecture lint — enforces directory boundaries and code quality rules.
Run: python scripts/arch_lint.py
Exits 0 if clean, 1 if violations found.
"""
import ast
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"

# ─── Rule 1: Import boundaries ───────────────────────────────────────────────
# core/ must not import from trading/, data/, backtest/, api/, notification/
IMPORT_RULES = {
    "app.core": {
        "deny": ["app.trading", "app.data", "app.backtest", "app.api", "app.notification"],
        "reason": "core/ must not depend on outer layers",
    },
}

# ─── Rule 2: File size limits ────────────────────────────────────────────────
MAX_LINES = 400

# ─── Rule 3: No hardcoded magic numbers ─────────────────────────────────────
FORBIDDEN_PATTERNS = [
    # (pattern, description, allowed_files)
    ("WARMUP = 220", "WARMUP hardcoded — use app.core.constants", ["app/core/constants.py"]),
    ("MAX_CANDLES_IN_RAM = 6000", "MAX_CANDLES hardcoded — use app.core.constants", ["app/core/constants.py"]),
]


def get_imports(filepath: Path) -> list[str]:
    """Extract all import module paths from a Python file."""
    try:
        tree = ast.parse(filepath.read_text(), filename=str(filepath))
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def check_import_boundaries() -> list[str]:
    """Check that import boundaries are respected."""
    violations = []
    for py_file in APP_DIR.rglob("*.py"):
        rel = py_file.relative_to(REPO_ROOT)
        module_path = str(rel).replace("/", ".").replace(".py", "").replace(".__init__", "")

        for boundary_prefix, rules in IMPORT_RULES.items():
            if not module_path.startswith(boundary_prefix):
                continue
            imports = get_imports(py_file)
            for imp in imports:
                for denied in rules["deny"]:
                    if imp.startswith(denied):
                        violations.append(
                            f"  {rel}: imports '{imp}' — {rules['reason']}"
                        )
    return violations


def check_file_sizes() -> list[str]:
    """Check no Python file exceeds MAX_LINES."""
    violations = []
    for py_file in APP_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        lines = py_file.read_text().count("\n") + 1
        if lines > MAX_LINES:
            rel = py_file.relative_to(REPO_ROOT)
            violations.append(f"  {rel}: {lines} lines (max {MAX_LINES})")
    return violations


def check_forbidden_patterns() -> list[str]:
    """Check for hardcoded magic numbers that should use constants."""
    violations = []
    for py_file in APP_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        rel = str(py_file.relative_to(REPO_ROOT))
        content = py_file.read_text()
        for pattern, desc, allowed in FORBIDDEN_PATTERNS:
            if pattern in content and rel not in allowed:
                violations.append(f"  {rel}: '{pattern}' — {desc}")
    return violations


def main():
    all_violations = []

    print("Checking import boundaries...")
    v = check_import_boundaries()
    if v:
        all_violations.extend(["Import boundary violations:"] + v)

    print("Checking file sizes...")
    v = check_file_sizes()
    if v:
        all_violations.extend([f"Files exceeding {MAX_LINES} lines:"] + v)

    print("Checking forbidden patterns...")
    v = check_forbidden_patterns()
    if v:
        all_violations.extend(["Hardcoded magic numbers:"] + v)

    if all_violations:
        print("\nArchitecture violations found:\n")
        for line in all_violations:
            print(line)
        print(f"\nTotal: {sum(1 for l in all_violations if l.startswith('  '))} violation(s)")
        return 1
    else:
        print("\nAll architecture checks passed.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
