# Compatibility Requirements - Backtest UI

> **Document Type:** Environment Constraints  
> **Agent:** security-auditor  
> **Status:** Phase 1 Documentation

---

## 1. Python Requirements

| Component | Version | Reason |
|-----------|---------|--------|
| **Python** | 3.10+ | Modern type hints, match statements |
| **Conda Environment** | `rsi` | Isolated dependencies |

### Required Packages

```txt
# requirements-ui.txt (new file)
pywebview>=5.0.0          # Desktop window
watchdog>=3.0.0           # File watching (dev mode)

# requirements.txt (existing, relevant subset)
pandas>=2.0.0             # Data manipulation
numpy>=1.24.0             # Numerical operations
pyyaml>=6.0.0             # Config parsing
ccxt>=4.0.0               # Exchange definitions
python-dateutil>=2.8.0    # Date parsing
```

---

## 2. Node.js Requirements (Development Only)

| Component | Version | Purpose |
|-----------|---------|---------|
| **Node.js** | 18+ LTS | Build tooling |
| **npm** | 9+ | Package management |

> ⚠️ **End users do NOT need Node.js.** It's only for building the React UI.

### package.json Version Locks

```json
{
  "engines": {
    "node": ">=18.0.0",
    "npm": ">=9.0.0"
  }
}
```

---

## 3. Operating System Support

| OS | Status | Notes |
|----|--------|-------|
| **Windows 10/11** | ✅ Primary | Main development/test platform |
| **macOS 12+** | ⚠️ Compatible | PyWebView uses WebKit |
| **Linux (Ubuntu 22+)** | ⚠️ Compatible | PyWebView uses GTK/WebKitGTK |

### Windows-Specific
- PowerShell 5.1+ for scripts
- Edge WebView2 (bundled with Windows 10+)

### macOS-Specific
- WebKit engine used (Safari-based)
- May need `pyobjc-framework-WebKit` for older macOS

### Linux-Specific
- Requires: `python3-gi`, `gir1.2-webkit2-4.0`
- Install: `sudo apt install python3-gi gir1.2-webkit2-4.0`

---

## 4. Browser Engine (Embedded)

PyWebView uses the system's native browser engine:

| OS | Engine | Notes |
|----|--------|-------|
| Windows | EdgeChromium (WebView2) | Modern, Chromium-based |
| macOS | WebKit | Safari engine |
| Linux | WebKitGTK | GTK integration |

### Implications for React UI
- Use standard web APIs only
- Avoid Chrome-specific features
- Test on all target platforms

---

## 5. Database Compatibility

| Database | Version | Location |
|----------|---------|----------|
| **SQLite** | 3.35+ | `data/backtest.db` |

### SQLite Features Used
- JSON functions (`json()`, `json_extract()`)
- Window functions
- UPSERT (`ON CONFLICT`)
- `STRICT` tables (optional)

### Python SQLite Module
```python
import sqlite3
# Built-in, no extra install needed
# Python 3.10+ includes SQLite 3.35+
```

---

## 6. File System Requirements

| Requirement | Path | Purpose |
|-------------|------|---------|
| **Read Access** | `app/backtest/data/` | CSV data files |
| **Write Access** | `config/strategy_overrides/` | JSON overrides |
| **Write Access** | `data/` | SQLite database |
| **Write Access** | `app/backtest/report/` | Generated reports |

### Disk Space
- Minimum: 100 MB free
- Recommended: 1 GB free (for large databases)

---

## 7. Environment Setup Script

### First-Time Setup (Developer)

```powershell
# 1. Create conda environment (if not exists)
conda create -n rsi python=3.11 -y
conda activate rsi

# 2. Install Python dependencies
pip install -r requirements.txt
pip install -r requirements-ui.txt

# 3. Install Node.js dependencies
cd ui
npm install

# 4. Build UI
npm run build

# 5. Initialize database
python cli/db_manager.py init
python cli/db_manager.py seed
```

### End User Setup

```powershell
# 1. Clone/download repository
git clone <repo> rsi_bot
cd rsi_bot

# 2. Create conda environment
conda env create -f environment.yml
conda activate rsi

# 3. Run application
.\run_backtest_ui.bat
```

---

## 8. Version Compatibility Matrix

| Component | Minimum | Tested | Maximum |
|-----------|---------|--------|---------|
| Python | 3.10 | 3.11 | 3.12 |
| PyWebView | 5.0 | 5.1 | - |
| React | 18.0 | 18.2 | 18.x |
| Node.js | 18.0 | 20.x | 22.x |
| SQLite | 3.35 | 3.42 | - |
| Windows | 10 (21H1) | 11 | - |

---

## 9. Known Incompatibilities

| Issue | Affected | Workaround |
|-------|----------|------------|
| Python 3.9 | Type hints | Upgrade to 3.10+ |
| Node.js 16 | Vite 5 | Upgrade to Node 18+ |
| SQLite 3.30 | JSON functions | Included with Python 3.10+ |
| macOS 10.x | PyWebView | Upgrade macOS or use different approach |

---

## 10. Testing Checklist

Before release, verify on:

- [ ] Windows 10 (clean install)
- [ ] Windows 11 (latest updates)
- [ ] Fresh conda environment
- [ ] No pre-existing Node.js
- [ ] First-time database creation
- [ ] Portable folder (no absolute paths)

---

## Cross-Reference

| Related Document | Purpose |
|------------------|---------|
| [SECURITY_RULES.md](./SECURITY_RULES.md) | Security constraints |
| [TECH_STACK.md](../architecture/TECH_STACK.md) | Technology decisions |
| [environment.yml](../../environment.yml) | Conda environment spec |
