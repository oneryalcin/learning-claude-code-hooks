# Claude Code Hooks Learning Lab

A dockerized environment for experimenting with Claude Code hooks and gaining full observability into Claude's behavior.

## Quick Start

```bash
cp .env.example .env        # Add your ANTHROPIC_API_KEY
make build                  # Build Docker image
make run                    # Run Claude interactively
```

In another terminal:
```bash
make logs                   # Tail logs with pretty JSON
```

## What This Does

Captures **every hook event** Claude Code emits and logs them to JSONL files with flattened fields for easy querying.

## Hook Events Captured

| Event | When It Fires | Key Fields |
|-------|---------------|------------|
| `SessionStart` | Session begins | `source` (startup/resume/clear) |
| `SessionEnd` | Session ends | `reason` |
| `UserPromptSubmit` | User sends a prompt | `prompt` |
| `PreToolUse` | Before tool executes | `tool_name`, `tool_input`, tool-specific fields |
| `PostToolUse` | After tool completes | `tool_name`, `tool_response`, tool-specific fields |
| `Stop` | Main agent finishes | `assistant_response` |
| `SubagentStop` | Subagent finishes | `agent_id`, `subagent_type`, `assistant_response` |
| `Notification` | Notifications sent | `message`, `notification_type` |
| `PreCompact` | Before context compaction | `trigger` (manual/auto) |

---

## Tutorial: Hook Outputs

### 1. SessionStart

Fires when Claude Code starts or resumes a session.

```json
{
  "ts": "2025-12-12T11:05:15Z",
  "session_id": "4a07e905-8520-4bdc-8186-96750a00bed2",
  "event": "SessionStart",
  "cwd": "/workspace",
  "source": "startup"
}
```

**Fields:**
- `source`: `"startup"` | `"resume"` | `"clear"` | `"compact"`

---

### 2. UserPromptSubmit

Fires when the user submits a prompt.

```json
{
  "ts": "2025-12-12T11:12:41Z",
  "session_id": "ddf1d6a3-29b5-42ad-81ae-670a9b7ba50a",
  "event": "UserPromptSubmit",
  "prompt": "Can you check the current working directory?",
  "cwd": "/workspace",
  "permission_mode": "default"
}
```

**Fields:**
- `prompt`: The exact user input

---

### 3. PreToolUse

Fires before any tool executes. Contains full tool parameters.

#### Bash Tool
```json
{
  "event": "PreToolUse",
  "tool_name": "Bash",
  "bash_command": "pwd",
  "bash_description": "Check current working directory",
  "bash_timeout": null,
  "bash_background": null
}
```

#### Write Tool
```json
{
  "event": "PreToolUse",
  "tool_name": "Write",
  "file_path": "/workspace/hello.py",
  "write_content_length": 42
}
```

#### Read Tool
```json
{
  "event": "PreToolUse",
  "tool_name": "Read",
  "file_path": "/workspace/config.json",
  "read_offset": null,
  "read_limit": null
}
```

#### Edit Tool
```json
{
  "event": "PreToolUse",
  "tool_name": "Edit",
  "file_path": "/workspace/app.py",
  "edit_replace_all": false
}
```

#### Grep Tool
```json
{
  "event": "PreToolUse",
  "tool_name": "Grep",
  "grep_pattern": "TODO",
  "grep_path": "/workspace",
  "grep_glob": "*.py",
  "grep_output_mode": "files_with_matches"
}
```

#### Glob Tool
```json
{
  "event": "PreToolUse",
  "tool_name": "Glob",
  "glob_pattern": "**/*.py",
  "glob_path": "/workspace"
}
```

#### WebSearch Tool
```json
{
  "event": "PreToolUse",
  "tool_name": "WebSearch",
  "search_query": "weather in London"
}
```

#### Task Tool (Subagent)
```json
{
  "event": "PreToolUse",
  "tool_name": "Task",
  "subagent_type": "general-purpose",
  "subagent_model": "haiku",
  "subagent_description": "Create fibonacci calculator",
  "subagent_run_in_background": true,
  "subagent_resume": null
}
```

---

### 4. PostToolUse

Fires after tool completes. Contains tool response.

#### Bash Response
```json
{
  "event": "PostToolUse",
  "tool_name": "Bash",
  "bash_command": "pwd",
  "tool_response": {
    "stdout": "/workspace",
    "stderr": "",
    "interrupted": false
  }
}
```

#### Write Response
```json
{
  "event": "PostToolUse",
  "tool_name": "Write",
  "file_path": "/workspace/hello.py",
  "tool_response": {
    "type": "create",
    "filePath": "/workspace/hello.py",
    "content": "print('Hello')\n"
  }
}
```

#### Task Response (Subagent)
```json
{
  "event": "PostToolUse",
  "tool_name": "Task",
  "agent_id": "a104625",
  "subagent_type": "general-purpose",
  "subagent_response": "I've created the file successfully..."
}
```

---

### 5. Stop

Fires when the main agent finishes responding. Includes the assistant's response extracted from the transcript.

```json
{
  "ts": "2025-12-12T11:29:48Z",
  "session_id": "5d93f26b-c34a-4254-859e-ce6618739838",
  "event": "Stop",
  "assistant_response": "The current working directory is `/workspace`.",
  "stop_hook_active": false
}
```

**Fields:**
- `assistant_response`: Claude's final text response (extracted from transcript)
- `stop_hook_active`: `true` if already in a stop hook (prevents loops)

---

### 6. SubagentStop

Fires when a subagent (Task) finishes. State tracking correlates `agent_id` with `subagent_type`.

```json
{
  "ts": "2025-12-12T11:25:41Z",
  "session_id": "d7659b04-bc15-491c-a30c-e4f4b57f729f",
  "event": "SubagentStop",
  "agent_id": "a104625",
  "subagent_type": "general-purpose",
  "subagent_description": "Create OHM model calculator Python file",
  "assistant_response": "I've created a simple Ohm's Law calculator...",
  "stop_hook_active": false
}
```

**Note:** Warmup agents (Explore/Plan spawned on startup) won't have `subagent_type` since they bypass the Task tool.

---

### 7. Notification

Fires when Claude sends notifications.

```json
{
  "ts": "2025-12-12T11:16:56Z",
  "session_id": "95770702-6a1b-4b52-acf0-cdb9e9208ad5",
  "event": "Notification",
  "message": "Claude is waiting for your input",
  "notification_type": "idle_prompt"
}
```

---

## Querying Logs

Logs are stored in `hooks/logs/` as JSONL files:
- `hooks-{session_id}.jsonl` - Per-session logs
- `latest.jsonl` - Symlink to current session

### Example Queries

```bash
# All events in current session
jq '.' hooks/logs/latest.jsonl

# Just user prompts
jq 'select(.event == "UserPromptSubmit") | .prompt' hooks/logs/latest.jsonl

# All bash commands
jq -r 'select(.bash_command) | "\(.ts) \(.bash_command)"' hooks/logs/latest.jsonl

# Failed bash commands
jq 'select(.tool_response.stderr != null and .tool_response.stderr != "")' hooks/logs/latest.jsonl

# All file writes
jq 'select(.tool_name == "Write") | {file: .file_path, len: .write_content_length}' hooks/logs/latest.jsonl

# Subagent activity
jq 'select(.subagent_type)' hooks/logs/latest.jsonl

# Assistant responses only
jq 'select(.assistant_response) | {event, response: .assistant_response[:100]}' hooks/logs/latest.jsonl

# Event counts
jq -r '.event' hooks/logs/latest.jsonl | sort | uniq -c
```

---

## Files

```
cchooks/
├── Dockerfile              # Debian + Claude Code + Python + jq
├── docker-compose.yml      # Mounts hooks, settings, workspace
├── Makefile                # build, run, shell, logs, clean
├── settings.json           # Hook configuration for all events
├── claude.json             # Claude Code config (skip onboarding)
├── hooks/
│   ├── logger.py           # Python logger with state tracking
│   └── logger.sh           # Original bash logger (unused)
└── hooks/logs/             # Generated logs (gitignored)
```

## How It Works

1. `settings.json` registers hooks for all 10 events
2. Each hook runs `logger.py` which receives JSON on stdin
3. Logger extracts key fields, flattens tool params, tracks agent state
4. Logs written to session-specific JSONL files
5. `latest.jsonl` symlink always points to current session

## State Tracking

The logger maintains `agent_state.json` to correlate `agent_id` with `subagent_type`:

1. **PreToolUse (Task)**: Stores pending task info
2. **SubagentStop**: Looks up agent, uses pending if not found
3. **PostToolUse (Task)**: Registers agent with full info

This handles the timing where SubagentStop fires before PostToolUse.
