#!/bin/bash
LOG_DIR="${CLAUDE_PROJECT_DIR:-$PWD}/hooks/logs"
mkdir -p "$LOG_DIR"

INPUT=$(cat)
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Extract session_id
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')
SESSION_FILE="$LOG_DIR/hooks-${SESSION_ID}.jsonl"

# Build log entry with key fields flattened
echo "$INPUT" | jq -c --arg ts "$TS" '{
  ts: $ts,
  session_id: .session_id,
  event: .hook_event_name,
  tool_name: .tool_name,
  tool_input: .tool_input,
  tool_response: .tool_response,
  prompt: .prompt,
  cwd: .cwd,
  permission_mode: .permission_mode
}' >> "$SESSION_FILE"

# Update latest.jsonl symlink
ln -sf "hooks-${SESSION_ID}.jsonl" "$LOG_DIR/latest.jsonl"

exit 0
