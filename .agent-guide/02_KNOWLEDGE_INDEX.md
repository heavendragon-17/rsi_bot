# Knowledge Index - When to Read What

> **For AI Agents** | Lazy loading guide for knowledge documents

---

## 🎯 Purpose

This document tells you **which knowledge documents to read and when**.

**DO NOT** read all knowledge docs upfront. This wastes tokens and causes context overload.

Each phase document will reference specific knowledge docs - read only those.

---

## 📚 Knowledge Document Catalog

### Core Knowledge (`.agent-guide/knowledge/`)

| File | When to Read | Content |
|------|--------------|---------|
| `API_REFERENCE.md` | Phase 2, 4 | All PyWebView API methods with signatures |
| `COMPONENT_SPECS.md` | Phase 5, 6, 7 | Behavior specs for each UI component |
| `TAILWIND_THEME.md` | Phase 4 | CSS variables and theming system |
| `DATABASE_SCHEMA.md` | Phase 1 | SQLite table definitions |
| `LESSONS_LEARNED.md` | Phase 0 | Gotchas, bugs, workarounds discovered |
| `FIGMA_MIGRATION.md` | Phase 5, 6, 7 | How to use Designstrategycommandcenter |

### Project Specs (`docs/`)

| File | When to Read | Content |
|------|--------------|---------|
| `docs/DATABASE.md` | Phase 1 | Full database schema (authoritative) |
| `docs/backend/API_CONTRACTS.md` | Phase 2, 3 | API method contracts |
| `docs/backend/FEATURE_GAPS.md` | Phase 3 | Backend features to implement |
| `docs/frontend/COMPONENT_MANIFEST.md` | Phase 5, 6, 7 | Component list and status |
| `docs/use-cases/USER_STORIES.md` | Any phase | User requirements |

---

## 📖 Phase → Knowledge Mapping

### Phase 0: Setup
- Read: `LESSONS_LEARNED.md` (for dependency gotchas)

### Phase 1: Database
- Read: `DATABASE_SCHEMA.md`
- Read: `docs/DATABASE.md`

### Phase 2: Bridge
- Read: `API_REFERENCE.md`
- Read: `docs/backend/API_CONTRACTS.md`

### Phase 3: Backend Features
- Read: `docs/backend/FEATURE_GAPS.md`
- Reference: `API_REFERENCE.md` (for method signatures)

### Phase 4: Frontend Core
- Read: `TAILWIND_THEME.md`
- Read: `API_REFERENCE.md` (for TypeScript types)

### Phase 5: Frontend Components
- Read: `COMPONENT_SPECS.md`
- Read: `FIGMA_MIGRATION.md`
- Reference: `docs/frontend/COMPONENT_MANIFEST.md`

### Phase 6: Frontend Charts
- Continue with `COMPONENT_SPECS.md`
- Reference: `FIGMA_MIGRATION.md`

### Phase 7: Frontend Analysis
- Continue with `COMPONENT_SPECS.md`
- Reference: previous analysis backend (Phase 3)

### Phase 8: Polish
- Read: Theme section of `TAILWIND_THEME.md`
- Read: Export section of `API_REFERENCE.md`

---

## 🔍 How to Use Knowledge Docs

1. **Before starting a phase**: Check this index for required reading
2. **Read the listed docs**: Load into context
3. **Execute the phase**: With knowledge available
4. **Clear context if needed**: After phase complete, you can forget phase-specific knowledge

---

## 📂 Existing Docs Reference

The `docs/` folder contains original specifications created during planning:

```
docs/
├── architecture/
│   ├── SYSTEM_OVERVIEW.md      # High-level architecture
│   ├── TECH_STACK.md           # Technology choices
│   └── COMPONENT_DIAGRAM.md    # Visual diagrams
├── backend/
│   ├── API_CONTRACTS.md        # API method specs
│   ├── FEATURE_GAPS.md         # Unimplemented features
│   └── ENDPOINT_CATALOG.md     # All endpoints
├── frontend/
│   ├── COMPONENT_MANIFEST.md   # Component list
│   └── STATE_MANAGEMENT.md     # Zustand patterns
├── use-cases/
│   ├── USER_STORIES.md         # User requirements
│   └── UI_WORKFLOWS.md         # User flows
└── DATABASE.md                 # SQLite schema
```

These are the "source of truth". The knowledge docs in `.agent-guide/knowledge/` are **distilled summaries** optimized for AI consumption.

---

**Next Step:** Read `phases/PHASE_0_SETUP.md` to begin work
