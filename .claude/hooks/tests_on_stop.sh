#!/usr/bin/env bash
# When Claude finishes a turn in which Python code changed, run the test suite.
# Plain English: before Claude hands back to Amrit, the 77+ unit tests rerun (about 5 seconds).
# If any fail, Claude is told which, and keeps working to fix them instead of stopping.
# Turns with no code changes (questions, docs) skip the run.
set -u
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

input=$(cat)
# Already continuing because of this hook: don't loop forever.
[ "$(echo "$input" | jq -r '.stop_hook_active // false')" = "true" ] && exit 0

# Only when Python files in the working tree differ from the last commit.
changed=$(git status --porcelain -- '*.py' 2>/dev/null)
[ -z "$changed" ] && exit 0

if out=$(.venv/bin/python -m pytest -q -x 2>&1); then
  exit 0
fi
summary=$(echo "$out" | grep -E "FAILED|ERROR|passed|failed" | tail -15)
jq -n --arg r "Tests are failing after your changes; fix them before finishing:
$summary" '{decision: "block", reason: $r}'
exit 0
