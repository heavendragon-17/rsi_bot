---
trigger: always_on
---

### 🧪 Testing & Backtesting Protocol

**1. File Organization (Strict)**

- **Directory Constraint:** ALL newly created test files or debug scripts must be saved in the `tests/` folder. Never create temporary test files in the root directory.
- **Path Awareness:** When running these files, remember to adjust imports or file paths to account for being inside the `tests/` subdirectory.

**2. Context & Preparation**

- **Source of Truth:** Before writing or running code, read `README_BACKTEST.md` to identify the correct arguments, flags, and data schemas.
- **Environment:** ALL commands must run within the `rsi` conda environment.

**3. Execution & Terminal Awareness**
_Check the active shell before executing commands:_

- **CMD / Bash:** Use `&&` (e.g., `source C:/ProgramData/miniconda3/Scripts/activate rsi`)
- **PowerShell:** Use `;` (e.g., `conda activate rsi; python tests/new_test.py`)
- **Universal Fallback:** If activation fails, use `conda run -n rsi python tests/new_test.py`
- **One-Liner Rule:** Always combine environment activation and script execution into a single command line.
