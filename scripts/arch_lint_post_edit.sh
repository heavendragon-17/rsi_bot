#!/usr/bin/env bash
# PostToolUse hook: run arch_lint.py after editing app/**/*.py files.
# Reads hook JSON from stdin, checks if the edited file is under app/.
# If violations found, outputs JSON with additionalContext for Claude.

set -euo pipefail

FILE=$(jq -r '.tool_input.file_path // .tool_response.filePath' 2>/dev/null)

# Only lint app/**/*.py files
if ! echo "$FILE" | grep -qE '/app/.*\.py$'; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT=$(python "$SCRIPT_DIR/arch_lint.py" 2>&1) && exit 0

# Lint failed — inject violations as context for Claude
# Escape the output for JSON
ESCAPED=$(echo "$OUTPUT" | python -c 'import sys,json; print(json.dumps(sys.stdin.read()))')

cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"arch_lint.py found violations after editing $FILE:\n$ESCAPED"}}
EOF
