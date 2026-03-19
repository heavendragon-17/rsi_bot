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
# Enforces the dependency DAG: core → (nothing), trading → core+data, etc.
IMPORT_RULES = {
    "app.core": {
        "deny": ["app.trading", "app.data", "app.backtest", "app.api", "app.notification"],
        "reason": "core/ must not depend on outer layers",
    },
    "app.trading": {
        "deny": ["app.backtest", "app.api", "app.notification"],
        "reason": "trading/ may only import from core/ and data/",
    },
}

# ─── Rule 2: File size limits ────────────────────────────────────────────────
MAX_LINES = 400

# ─── Rule 3: No hardcoded magic numbers ─────────────────────────────────────
FORBIDDEN_PATTERNS = [
    # (pattern, description, allowed_files)
    ("WARMUP = 220", "WARMUP hardcoded — use app.core.constants", ["app/core/constants.py"]),
    ("MAX_CANDLES_IN_RAM = 6000", "MAX_CANDLES hardcoded — use app.core.constants", ["app/core/constants.py"]),
    ("load_dotenv()", "dotenv loaded outside main.py — load once at entry point", ["main.py"]),
]

# ─── Rule 4: Directory whitelist ─────────────────────────────────────────────
# Only these top-level dirs allowed under app/. Prevents new dirs appearing.
ALLOWED_APP_DIRS = {
    "core", "trading", "data", "backtest", "api", "notification", "repository",
    "__pycache__",
}

# ─── Rule 5: core/ file whitelist ────────────────────────────────────────────
# Only contracts/models in core/. Prevents "core gravity" anti-pattern.
ALLOWED_CORE_FILES = {
    "__init__.py", "interfaces.py", "actions.py", "analysis_result.py",
    "config.py", "constants.py", "context.py", "events.py", "exceptions.py",
    "logging.py", "snapshots.py", "utils.py",
}


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


def check_directory_whitelist() -> list[str]:
    """Prevent new top-level dirs appearing under app/ (the 'just add a folder' drift)."""
    violations = []
    for item in APP_DIR.iterdir():
        if item.is_dir() and item.name not in ALLOWED_APP_DIRS:
            rel = item.relative_to(REPO_ROOT)
            violations.append(
                f"  {rel}/ is not an allowed app/ directory. "
                f"Allowed: {sorted(ALLOWED_APP_DIRS - {'__pycache__'})}"
            )
    return violations


def check_core_file_whitelist() -> list[str]:
    """Prevent 'core gravity' — new implementation files landing in core/."""
    violations = []
    core_dir = APP_DIR / "core"
    if not core_dir.exists():
        return violations
    for py_file in core_dir.glob("*.py"):
        if py_file.name not in ALLOWED_CORE_FILES:
            rel = py_file.relative_to(REPO_ROOT)
            violations.append(
                f"  {rel} is not allowed in core/. "
                f"core/ is only for contracts and models. "
                f"Move implementation to the appropriate domain dir."
            )
    return violations


def check_class_count(max_classes: int = 1) -> list[str]:
    """Prevent god files: max 1 real class per file (dataclasses/enums don't count)."""
    violations = []
    for py_file in APP_DIR.rglob("*.py"):
        if "__pycache__" in str(py_file) or "__init__" in py_file.name:
            continue
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except SyntaxError:
            continue

        real_classes = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Skip dataclasses, enums, and small classes (< 5 methods)
            decorators = [
                d.id if isinstance(d, ast.Name) else
                d.attr if isinstance(d, ast.Attribute) else ""
                for d in node.decorator_list
            ]
            is_dataclass = "dataclass" in decorators
            # Check if it inherits from Enum
            is_enum = any(
                (isinstance(b, ast.Name) and "Enum" in b.id) or
                (isinstance(b, ast.Attribute) and "Enum" in b.attr)
                for b in node.bases
            )
            if is_dataclass or is_enum:
                continue
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if len(methods) >= 3:  # Only count classes with 3+ methods as "real"
                real_classes.append(node.name)

        if len(real_classes) > max_classes:
            rel = py_file.relative_to(REPO_ROOT)
            violations.append(
                f"  {rel}: {len(real_classes)} classes ({', '.join(real_classes)}) — max {max_classes} per file"
            )
    return violations


def main():
    all_violations = []
    checks = [
        ("Checking import boundaries...", "Import boundary violations:", check_import_boundaries),
        ("Checking file sizes...", f"Files exceeding {MAX_LINES} lines:", check_file_sizes),
        ("Checking forbidden patterns...", "Forbidden patterns:", check_forbidden_patterns),
        ("Checking directory whitelist...", "Unauthorized directories:", check_directory_whitelist),
        ("Checking core/ whitelist...", "Unauthorized files in core/:", check_core_file_whitelist),
        ("Checking class count per file...", "Files with too many classes:", check_class_count),
    ]

    for msg, header, check_fn in checks:
        print(msg)
        v = check_fn()
        if v:
            all_violations.extend([header] + v)

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
