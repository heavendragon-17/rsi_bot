# Security Rules - Backtest UI

> **Document Type:** Security Constraints  
> **Agent:** security-auditor  
> **Status:** Phase 1 Documentation

---

## 1. Threat Model

| Threat | Risk Level | Mitigation |
|--------|------------|------------|
| Malicious config injection | LOW | Input validation, type checking |
| Arbitrary file access | MEDIUM | Whitelist allowed paths |
| Code execution via UI | HIGH | No eval(), no dynamic imports |
| Strategy file corruption | CRITICAL | JSON overrides only, no .py writes |

> **Context:** This is a LOCAL desktop application. Network-based threats are out of scope.

---

## 2. Config Editing Safety

### 🔴 CRITICAL RULE: NO PYTHON FILE EDITS

```
❌ NEVER: UI writes to app/strategies/*.py
✅ ALWAYS: UI writes to config/strategy_overrides/*.json
```

### Allowed Write Operations

| Target | Permission | Format |
|--------|------------|--------|
| `config/strategy_overrides/{name}.json` | ✅ WRITE | JSON |
| `config/config.yaml` | ✅ WRITE | YAML |
| `data/backtest.db` | ✅ WRITE | SQLite |

### Forbidden Write Operations

| Target | Permission | Reason |
|--------|------------|--------|
| `app/strategies/*.py` | ❌ NEVER | Code integrity |
| `app/backtest/*.py` | ❌ NEVER | Code integrity |
| Any `*.py` file | ❌ NEVER | Code integrity |
| System files | ❌ NEVER | System integrity |

---

## 3. File Access Boundaries

### Read Whitelist

```python
ALLOWED_READ_PATHS = [
    "app/backtest/data/*.csv",           # Historical data
    "config/*.yaml",                      # Global config
    "config/strategy_overrides/*.json",  # Strategy overrides
    "data/backtest.db",                  # Results database
    "app/strategies/*.py",               # Read for DEFAULT_CONFIG (introspection)
]
```

### Write Whitelist

```python
ALLOWED_WRITE_PATHS = [
    "config/strategy_overrides/*.json",  # Strategy overrides
    "config/config.yaml",                # Global config (validated)
    "data/backtest.db",                  # Results database
    "app/backtest/report/*.html",        # Generated reports
    "app/backtest/report/*.csv",         # Exported trades
]
```

### Implementation Pattern

```python
# app/ui_bridge/security.py

from pathlib import Path
import fnmatch

PROJECT_ROOT = Path(__file__).parent.parent.parent

WRITE_WHITELIST = [
    "config/strategy_overrides/*.json",
    "config/config.yaml",
    "data/backtest.db",
    "app/backtest/report/*",
]

def is_write_allowed(path: Path) -> bool:
    """Check if write operation is allowed."""
    try:
        rel_path = path.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        return False  # Outside project root
    
    rel_str = str(rel_path).replace("\\", "/")
    return any(fnmatch.fnmatch(rel_str, pattern) for pattern in WRITE_WHITELIST)
```

---

## 4. Input Validation Rules

### Numeric Inputs

| Parameter Type | Validation |
|----------------|------------|
| Integer | `isinstance(v, int)`, min/max bounds |
| Float | `isinstance(v, (int, float))`, min/max bounds |
| Percentage | `0.0 <= v <= 100.0` |
| Ratio | `v > 0` |

### String Inputs

| Input Type | Validation |
|------------|------------|
| Strategy name | Must exist in `STRATEGY_MAP` |
| File path | Must match whitelist pattern |
| Symbol | Regex: `^[A-Z0-9]+/[A-Z]+$` |

### Implementation Pattern

```python
# app/ui_bridge/validation.py

from typing import Any, Dict
from decimal import Decimal

def validate_strategy_config(config: Dict[str, Any], schema: Dict[str, Any]) -> list:
    """Validate config against schema. Returns list of errors."""
    errors = []
    
    for key, value in config.items():
        if key not in schema:
            errors.append(f"Unknown parameter: {key}")
            continue
        
        spec = schema[key]
        
        # Type check
        if spec["type"] == "number":
            if not isinstance(value, (int, float, Decimal)):
                errors.append(f"{key}: must be a number")
                continue
            
            # Range check
            if "min" in spec and value < spec["min"]:
                errors.append(f"{key}: must be >= {spec['min']}")
            if "max" in spec and value > spec["max"]:
                errors.append(f"{key}: must be <= {spec['max']}")
    
    return errors
```

---

## 5. Process Isolation

### Desktop App Model
- Single-process Python application
- UI and backtest run in same process
- No network communication required
- No authentication needed (local only)

### Long-Running Tasks
- Backtest runs synchronously on main thread
- UI shows progress indicator (not frozen)
- Cancel button available (sets flag)
- 
```python
class BacktestRunner:
    def __init__(self):
        self._cancel_requested = False
    
    def run(self, params):
        for i, row in enumerate(data):
            if self._cancel_requested:
                raise CancelledError("Backtest cancelled by user")
            # ... process row
    
    def cancel(self):
        self._cancel_requested = True
```

---

## 6. Future VPS UI Separation

> ⚠️ **IMPORTANT:** Local Backtest UI and VPS Config UI are SEPARATE projects.

| Feature | Local Backtest UI | VPS Config UI (Future) |
|---------|-------------------|------------------------|
| Network | ❌ Offline | ✅ Internet required |
| API Keys | ❌ None | ✅ Exchange API keys |
| SSH | ❌ None | ✅ VPS connection |
| Auth | ❌ None | ✅ User authentication |
| Database | Local SQLite | Remote PostgreSQL |

**Separation Rule:** Do NOT add any VPS, API, or network features to the Backtest UI.

---

## 7. Secret Management

### No Secrets in Backtest UI
- No API keys stored or used
- No SSH credentials
- No authentication tokens

### Future VPS UI (Out of Scope)
```
# This is NOT for Backtest UI!
# Future VPS UI would use:
config/secrets.yaml  # .gitignored
config/vps_config.yaml  # Connection settings
```

---

## 8. Audit Trail

### Database Logging
All backtest runs are logged to SQLite with:
- `git_hash`: Commit at time of run
- `version`: Application version
- `created_at`: Timestamp
- `config_json`: Full config snapshot

### Why?
- Reproducibility: Can recreate exact test conditions
- Debugging: Track when bugs were introduced
- Compliance: Audit trail for strategy validation

---

## 9. Security Checklist for Implementation

Before merging any code:

- [ ] No `eval()` or `exec()` calls
- [ ] No dynamic `import` from user input
- [ ] All file writes checked against whitelist
- [ ] All user inputs validated before use
- [ ] No `.py` files written by UI
- [ ] No network requests in backtest path
- [ ] Database queries use parameterized statements
- [ ] Error messages don't leak file paths

---

## Cross-Reference

| Related Document | Purpose |
|------------------|---------|
| [COMPATIBILITY.md](./COMPATIBILITY.md) | Environment requirements |
| [backtest-ui.md](../../.agent/rules/backtest-ui.md) | Agent enforcement rules |
| [DATABASE.md](../DATABASE.md) | Audit trail schema |
