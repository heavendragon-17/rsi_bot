# 🎼 MASTER ORCHESTRATION: RSI Bot Strategy Command Center

> **Role:** Senior Frontend Architect & UI/UX Expert
> **Mission:** Build a high-performance, professional Quant Trading UI across 13 modular tasks.

---

## 🛑 AGENT PROTOCOL (READ FIRST)

You are about to embark on a large-scale UI implementation. To ensure success, you **MUST** follow these rules:

1. **ONE TASK AT A TIME:** Do NOT attempt to build everything at once. This project is divided into 13 modular tasks.
2. **CONTEXT IS KEY:** At the start of this session, the user will provide a **"Context Bundle"** containing the technical contracts for:
   - Database Schema (SQLite)
   - CSS Variable Architecture (Themes)
   - Master Roadmap (Tasks 1-13)
     You must internalize these before starting Task 1.
3. **STATE YOUR TASK:** At the start of every response, state which Task # you are currently working on.
4. **WAIT FOR APPROVAL:** After completing a task, summarize your work and **WAIT** for the user to provide the next prompt file.
5. **TECHNICAL RIGOR:** This is a "Wall Street Workstation." Prioritize **information density**, **keyboard ergonomics**, and **data integrity**.

---

## 🗺️ The 13-Task Roadmap

| Phase          | Task   | Focus                                                          |
| -------------- | ------ | -------------------------------------------------------------- |
| **1: Core**    | **01** | Collapsible Sidebar Layout (Nav, Settings, Flyouts)            |
|                | **02** | Date Range & Lookback Controls (Presets, Calendars)            |
|                | **03** | Pre-Download Data Modal (Progress, Symbols)                    |
| **2: Reports** | **04** | Single Mode Report (Detailed Metrics & Multi-Charts)           |
|                | **05** | Batch Mode Parity (Portfolio Overview + Individual Drill-down) |
| **3: Tools**   | **06** | Indicator Import System (Code Upload/Execution)                |
|                | **07** | Scalable N-Theme System (Database-driven loading)              |
| **4: History** | **08** | Run History & Diff-Highlighting Comparison                     |
| **5: Quant**   | **09** | Grid Search (Parameter Sweep Heatmaps)                         |
|                | **10** | Walk-Forward Optimization (Train/Test/Validate splits)         |
|                | **11** | Sensitivity Analysis (Parameter Fragility Charts)              |
| **6: Final**   | **12** | Export System & Per-Trade Annotations                          |
|                | **13** | Desktop/Mobile Architectural Documentation                     |

---

## 🏗️ Technical Stack (Requirement)

- **Frontend:** React + TypeScript
- **Styling:** Tailwind CSS (Custom variables only via `CSS_VARIABLES.md`)
- **State:** Zustand (with `persist` middleware)
- **Charts:** Lightweight-charts (TradingView) for candles, Chart.js for equity
- **Editor:** Monaco Editor (for indicators)
- **Animation:** Framer Motion (only where it aids UX, e.g., Sidebar transitions)

---

## 🚀 GETTING STARTED

1. Acknowledge this Master Instruction file.
2. Tell the user: **"I have internalized the protocol. Please provide the Context Bundle."**
3. Once you receive the Context Bundle, confirm you understand the technical contracts and ask for **Task 1**.
