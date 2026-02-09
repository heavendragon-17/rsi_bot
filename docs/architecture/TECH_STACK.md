# Technology Stack - Backtest UI

> **Document Type:** Technology Decisions  
> **Agent:** project-planner  
> **Status:** Phase 1 Documentation

---

## 1. Stack Overview

| Layer | Technology | Version | Rationale |
|-------|------------|---------|-----------|
| **Desktop Shell** | PyWebView | 5.x | Python-native, no Rust needed |
| **Frontend** | React | 18.x | Existing UI, component ecosystem |
| **Language (UI)** | TypeScript | 5.x | Type safety, editor support |
| **State Management** | Zustand | 4.x | Lightweight, existing choice |
| **Charts** | lightweight-charts | 4.x | TradingView library, existing |
| **Build Tool** | Vite | 5.x | Fast builds, existing |
| **Styling** | Tailwind CSS | 3.x | Utility-first, existing |
| **Backend** | Python | 3.10+ | Type hints, async support |
| **Database** | SQLite | 3.x | Local, zero config, portable |
| **Config** | YAML + JSON | - | Human-readable, structured |

---

## 2. Decision: Desktop Framework

### Options Evaluated

| Option | Pros | Cons | Score |
|--------|------|------|-------|
| **PyWebView** ✅ | Python-native, simple, no HTTP | Limited native features | 8/10 |
| Tauri + Sidecar | Small binary, modern | Rust compilation, complexity | 6/10 |
| Electron | Mature, full Chromium | Large binary (~150MB), Node.js | 5/10 |
| Qt for Python | Native widgets | Different paradigm, learning curve | 4/10 |

### Decision: PyWebView

**Primary Reasons:**
1. **No Rust/C++ Toolchain** - User's constraint
2. **Direct Python↔JS** - No HTTP server needed
3. **Existing Python Codebase** - Reuse backtest engine
4. **Simple Distribution** - `.bat` script or PyInstaller

---

## 3. Decision: State Management

### Options Evaluated

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Zustand** ✅ | Simple, lightweight, existing | Less structured | KEEP |
| Redux Toolkit | Structured, middleware | Heavier, migration cost | SKIP |
| Jotai | Atomic, minimal | Different paradigm | SKIP |

**Decision:** Keep Zustand (already in Figma UI)

---

## 4. Decision: Chart Library

### Options Evaluated

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **lightweight-charts** ✅ | TradingView quality, existing | Limited customization | KEEP |
| Recharts | React-native, flexible | Less financial focus | SKIP |
| ECharts | Powerful, many chart types | Heavier bundle | SKIP |

**Decision:** Keep lightweight-charts (already in Figma UI)

---

## 5. Decision: Database

### Options Evaluated

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **SQLite** ✅ | Zero config, portable, fast | Single writer | USE |
| DuckDB | Analytics optimized | Newer, less ecosystem | FUTURE |
| JSON Files | Simple | No querying, slow at scale | SKIP |

**Decision:** SQLite with schema from `docs/DATABASE.md`

---

## 6. Python Dependencies

```txt
# requirements-ui.txt (new)
pywebview>=5.0
watchdog>=3.0        # File watcher for dev mode

# requirements.txt (existing)
pandas>=2.0
numpy>=1.24
pyyaml>=6.0
ccxt>=4.0            # Already pinned
```

---

## 7. Node.js Dependencies (UI Build Only)

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "zustand": "^4.4.0",
    "lightweight-charts": "^4.1.0",
    "framer-motion": "^10.0.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "@types/react": "^18.2.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

> ⚠️ **Note:** Node.js is development-only. End users don't need it.

---

## 8. Environment Requirements

| Requirement | Development | End User |
|-------------|-------------|----------|
| Python 3.10+ | ✅ Required | ✅ Required |
| Conda (rsi env) | ✅ Required | ✅ Required |
| Node.js 18+ | ✅ Required | ❌ Not needed |
| Git | ✅ Required | ❌ Not needed |
| VS Code | ✅ Recommended | ❌ Not needed |

---

## 9. Cross-Reference

| Related Document | Purpose |
|------------------|---------|
| [SYSTEM_OVERVIEW.md](./SYSTEM_OVERVIEW.md) | Architecture context |
| [COMPATIBILITY.md](../constraints/COMPATIBILITY.md) | Version constraints |
| [DATABASE.md](../DATABASE.md) | SQLite schema |
