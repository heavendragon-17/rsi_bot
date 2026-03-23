#!/bin/bash
# Pre-commit architecture check for Claude Code
# Blocks commits that introduce NEW architecture violations.
# Baseline is stored in .claude/arch_baseline.txt

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASELINE="$REPO_ROOT/.claude/arch_baseline.txt"
cd "$REPO_ROOT"
CURRENT=$(python scripts/arch_lint.py 2>&1)
CURRENT_COUNT=$(echo "$CURRENT" | grep -c "^  ")

if [ ! -f "$BASELINE" ]; then
  # No baseline yet — record current violations and allow
  echo "$CURRENT_COUNT" > "$BASELINE"
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"arch_lint: baseline recorded with '"$CURRENT_COUNT"' existing violations. Future commits that increase this count will be blocked."}}'
  exit 0
fi

BASELINE_COUNT=$(cat "$BASELINE" 2>/dev/null || echo "0")

if [ "$CURRENT_COUNT" -gt "$BASELINE_COUNT" ]; then
  # New violations introduced — block
  DIFF=$((CURRENT_COUNT - BASELINE_COUNT))
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"arch_lint: '"$DIFF"' NEW architecture violation(s) introduced (was '"$BASELINE_COUNT"', now '"$CURRENT_COUNT"'). Run python scripts/arch_lint.py to see details. Fix violations before committing."}}'
  exit 0
elif [ "$CURRENT_COUNT" -lt "$BASELINE_COUNT" ]; then
  # Violations reduced — update baseline
  echo "$CURRENT_COUNT" > "$BASELINE"
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"arch_lint: violations reduced from '"$BASELINE_COUNT"' to '"$CURRENT_COUNT"'. Baseline updated."}}'
  exit 0
else
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"arch_lint: no new violations ('"$CURRENT_COUNT"' existing)."}}'
  exit 0
fi
