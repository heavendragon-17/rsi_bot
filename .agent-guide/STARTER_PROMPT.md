# Jules Starter Prompt

> **Copy and paste this entire block to start the AI agent.**

---

I need you to rebuild the Backtest UI for my RSI Bot project.

**Read the documentation in `.agent-guide/` folder first, in this order:**

1. `.agent-guide/00_MASTER_GUIDE.md` - Start here
2. `.agent-guide/01_ARCHITECTURE.md` - Understand structure
3. `.agent-guide/02_KNOWLEDGE_INDEX.md` - Learn when to read other docs

**Important Execution Rules:**
- Execute phases sequentially (Start with Phase 0).
- After completing a phase, **RUN THE VERIFICATION STEPS**.
- **IF VERIFICATION PASSES:** Report success and **IMMEDIATELY PROCEED** to the next phase without asking.
- **IF VERIFICATION FAILS:** STOP, report the error, and wait for my instructions.
- Load knowledge docs only when the phase doc tells you to.
- The `Designstrategycommandcenter/` folder is Figma-generated UI - copy styles, rewrite logic.

**Start with Phase 0:**
Read `.agent-guide/phases/PHASE_0_SETUP.md` and execute it.
Then proceed automatically through Phase 8 if everything passes.
