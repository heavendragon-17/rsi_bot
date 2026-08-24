# Lessons Learned

## 2026-08-20: Treat an annotated roadmap selection as implementation scope

- **Mistake**: Interpreted execution-policy answers as a documentation-only request after presenting an implementation roadmap.
- **Rule**: When the user selects roadmap items or says "these ones," turn the selected items into the active implementation checklist and execute them. Use later policy answers to resolve implementation boundaries, not to narrow the request unless the user says so.
- **Files affected**: `tasks/todo.md`, Core V2.1 implementation and documentation.

## 2026-08-20: Prefer the user's existing project environment

- **Correction**: The user identified the intended Conda installation and asked to use its `rsi` environment for this repository.
- **Rule**: Inspect and reuse the named project environment before creating a new one. Record its actual interpreter/dependency versions rather than preserving an earlier assumed version requirement.
- **Files affected**: project setup documentation and test commands.

> Patterns captured from user corrections. Review at session start. Update after every correction.

<!-- Example:
## 2024-01-15: Always check for None before accessing .symbol
- **Mistake**: Assumed position was never None in backtest context
- **Rule**: Always guard `position` access with a None check — backtest engine passes None for flat positions
- **Files affected**: app/strategies/*.py
-->
