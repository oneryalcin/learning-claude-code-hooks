#!/usr/bin/env python3
"""
Claude Code hook logger - logs all hook events to JSONL files.
Handles transcript reading for Stop events and subagent response extraction.
Uses state tracking to correlate agent_id with subagent_type.
"""
import json
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
import fcntl


def get_last_assistant_message(transcript_path: str) -> str:
    """Extract last assistant message from transcript JSONL."""
    if not transcript_path or not os.path.exists(transcript_path):
        return ""

    last_assistant = ""
    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("type") == "assistant":
                        message = entry.get("message", {})
                        content = message.get("content", [])
                        texts = []
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                texts.append(block.get("text", ""))
                        if texts:
                            last_assistant = "\n".join(texts)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return last_assistant


def extract_task_response(tool_response: dict) -> str:
    """Extract text content from Task tool response."""
    if not tool_response:
        return ""

    content = tool_response.get("content", [])
    texts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            texts.append(block.get("text", ""))
    return "\n".join(texts) if texts else ""


class AgentStateTracker:
    """Track agent_id → subagent_type mapping across hook invocations."""

    def __init__(self, state_dir: Path):
        self.state_file = state_dir / "agent_state.json"
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _read_state(self) -> dict:
        """Read state with file locking."""
        if not self.state_file.exists():
            return {}
        try:
            with open(self.state_file, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return data
        except (json.JSONDecodeError, IOError):
            return {}

    def _write_state(self, state: dict):
        """Write state with file locking."""
        try:
            with open(self.state_file, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(state, f)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except IOError:
            pass

    def register_agent(self, agent_id: str, subagent_type: str, model: str = None, description: str = None):
        """Register an agent with its type."""
        if not agent_id:
            return
        state = self._read_state()
        state[agent_id] = {
            "subagent_type": subagent_type,
            "model": model,
            "description": description,
            "registered_at": datetime.now(timezone.utc).isoformat()
        }
        # Keep only last 100 agents to prevent unbounded growth
        if len(state) > 100:
            sorted_agents = sorted(state.items(), key=lambda x: x[1].get("registered_at", ""))
            state = dict(sorted_agents[-100:])
        self._write_state(state)

    def set_pending_task(self, session_id: str, subagent_type: str, model: str = None, description: str = None):
        """Store pending task info (before agent_id is known)."""
        state = self._read_state()
        state[f"pending_{session_id}"] = {
            "subagent_type": subagent_type,
            "model": model,
            "description": description,
            "registered_at": datetime.now(timezone.utc).isoformat()
        }
        self._write_state(state)

    def get_and_clear_pending_task(self, session_id: str) -> dict:
        """Get and clear pending task info."""
        state = self._read_state()
        key = f"pending_{session_id}"
        info = state.pop(key, {})
        if info:
            self._write_state(state)
        return info

    def lookup_agent(self, agent_id: str) -> dict:
        """Lookup agent info by agent_id."""
        if not agent_id:
            return {}
        state = self._read_state()
        return state.get(agent_id, {})


def main():
    # Setup log directory
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    log_dir = Path(project_dir) / "hooks" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Initialize state tracker
    tracker = AgentStateTracker(log_dir)

    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)  # Silent fail, don't block Claude

    # Extract common fields
    session_id = input_data.get("session_id", "unknown")
    event = input_data.get("hook_event_name", "unknown")
    tool_name = input_data.get("tool_name")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Get tool_input
    tool_input = input_data.get("tool_input") or {}

    # Build log entry with flattened key fields
    log_entry = {
        "ts": ts,
        "session_id": session_id,
        "event": event,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "prompt": input_data.get("prompt"),
        "cwd": input_data.get("cwd"),
        "permission_mode": input_data.get("permission_mode"),
    }

    # Flatten tool-specific params for easier filtering
    if tool_input:
        # Task tool
        if tool_name == "Task":
            log_entry["subagent_type"] = tool_input.get("subagent_type")
            log_entry["subagent_model"] = tool_input.get("model")
            log_entry["subagent_description"] = tool_input.get("description")
            log_entry["subagent_run_in_background"] = tool_input.get("run_in_background")
            log_entry["subagent_resume"] = tool_input.get("resume")

            # On PreToolUse, store as pending (agent_id not known yet)
            if event == "PreToolUse":
                tracker.set_pending_task(
                    session_id=session_id,
                    subagent_type=tool_input.get("subagent_type"),
                    model=tool_input.get("model"),
                    description=tool_input.get("description")
                )

        # Bash tool
        elif tool_name == "Bash":
            log_entry["bash_command"] = tool_input.get("command")
            log_entry["bash_description"] = tool_input.get("description")
            log_entry["bash_timeout"] = tool_input.get("timeout")
            log_entry["bash_background"] = tool_input.get("run_in_background")
            log_entry["bash_no_sandbox"] = tool_input.get("dangerouslyDisableSandbox")

        # Read tool
        elif tool_name == "Read":
            log_entry["file_path"] = tool_input.get("file_path")
            log_entry["read_offset"] = tool_input.get("offset")
            log_entry["read_limit"] = tool_input.get("limit")

        # Write tool
        elif tool_name == "Write":
            log_entry["file_path"] = tool_input.get("file_path")
            # content can be large, just note its length
            content = tool_input.get("content", "")
            log_entry["write_content_length"] = len(content) if content else 0

        # Edit tool
        elif tool_name == "Edit":
            log_entry["file_path"] = tool_input.get("file_path")
            log_entry["edit_replace_all"] = tool_input.get("replace_all")

        # Grep tool
        elif tool_name == "Grep":
            log_entry["grep_pattern"] = tool_input.get("pattern")
            log_entry["grep_path"] = tool_input.get("path")
            log_entry["grep_glob"] = tool_input.get("glob")
            log_entry["grep_output_mode"] = tool_input.get("output_mode")

        # Glob tool
        elif tool_name == "Glob":
            log_entry["glob_pattern"] = tool_input.get("pattern")
            log_entry["glob_path"] = tool_input.get("path")

        # WebSearch tool
        elif tool_name == "WebSearch":
            log_entry["search_query"] = tool_input.get("query")

        # WebFetch tool
        elif tool_name == "WebFetch":
            log_entry["fetch_url"] = tool_input.get("url")

        # TaskOutput tool
        elif tool_name == "TaskOutput":
            log_entry["task_output_id"] = tool_input.get("task_id")
            log_entry["task_output_block"] = tool_input.get("block")
            log_entry["task_output_timeout"] = tool_input.get("timeout")

    # For PostToolUse, handle tool_response specially
    if event == "PostToolUse":
        tool_response = input_data.get("tool_response")

        # For Task tool, extract subagent response text and agent_id
        if tool_name == "Task" and tool_response:
            agent_id = tool_response.get("agentId")
            log_entry["agent_id"] = agent_id
            log_entry["subagent_response"] = extract_task_response(tool_response)[:5000]

            # Register agent for later lookup in SubagentStop
            if agent_id and tool_input:
                tracker.register_agent(
                    agent_id=agent_id,
                    subagent_type=tool_input.get("subagent_type"),
                    model=tool_input.get("model"),
                    description=tool_input.get("description")
                )
        else:
            # For other tools, include full response
            log_entry["tool_response"] = tool_response

    # For Stop, extract assistant response from transcript
    if event == "Stop":
        transcript_path = input_data.get("transcript_path", "")
        response = get_last_assistant_message(transcript_path)
        log_entry["assistant_response"] = response[:5000] if response else None
        log_entry["stop_hook_active"] = input_data.get("stop_hook_active")

    # For SubagentStop, try agent_transcript_path first, then transcript_path
    if event == "SubagentStop":
        # Try agent-specific transcript first
        transcript_path = input_data.get("agent_transcript_path") or input_data.get("transcript_path", "")
        response = get_last_assistant_message(transcript_path)
        log_entry["assistant_response"] = response[:5000] if response else None
        agent_id = input_data.get("agent_id")
        log_entry["agent_id"] = agent_id
        log_entry["stop_hook_active"] = input_data.get("stop_hook_active")

        # Lookup agent info from state tracker
        agent_info = tracker.lookup_agent(agent_id)
        if agent_info:
            log_entry["subagent_type"] = agent_info.get("subagent_type")
            log_entry["subagent_model"] = agent_info.get("model")
            log_entry["subagent_description"] = agent_info.get("description")
        else:
            # Fallback to pending task (SubagentStop fires before PostToolUse)
            pending = tracker.get_and_clear_pending_task(session_id)
            if pending:
                log_entry["subagent_type"] = pending.get("subagent_type")
                log_entry["subagent_model"] = pending.get("model")
                log_entry["subagent_description"] = pending.get("description")
                # Also register the agent now that we know the id
                tracker.register_agent(
                    agent_id=agent_id,
                    subagent_type=pending.get("subagent_type"),
                    model=pending.get("model"),
                    description=pending.get("description")
                )

    # For SessionStart/SessionEnd, capture source/reason
    if event == "SessionStart":
        log_entry["source"] = input_data.get("source")
    if event == "SessionEnd":
        log_entry["reason"] = input_data.get("reason")

    # For Notification, capture message and type
    if event == "Notification":
        log_entry["message"] = input_data.get("message")
        log_entry["notification_type"] = input_data.get("notification_type")

    # For PreCompact, capture trigger
    if event == "PreCompact":
        log_entry["trigger"] = input_data.get("trigger")

    # Remove None values for cleaner output
    log_entry = {k: v for k, v in log_entry.items() if v is not None}

    # Write to session-specific file
    session_file = log_dir / f"hooks-{session_id}.jsonl"
    with open(session_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Update latest.jsonl symlink
    latest_link = log_dir / "latest.jsonl"
    try:
        latest_link.unlink(missing_ok=True)
        latest_link.symlink_to(f"hooks-{session_id}.jsonl")
    except Exception:
        pass  # Symlink update is best-effort

    sys.exit(0)


if __name__ == "__main__":
    main()
