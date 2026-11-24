#!/usr/bin/env bash
# After Claude edits or writes a Python file, lint that file with ruff.
# Plain English: a one-second spell-check for code. If ruff finds a problem, the message goes
# straight back to Claude (exit code 2), so the mistake is fixed in the same turn.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

file=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')
case "$file" in
  *.py) ;;
  *) exit 0 ;;          # not Python: nothing to check
esac
[ -f "$file" ] || exit 0

if ! out=$(.venv/bin/ruff check "$file" 2>&1); then
  echo "ruff found problems in $file:" >&2
  echo "$out" >&2
  exit 2
fi
exit 0
