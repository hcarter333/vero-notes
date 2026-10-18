#!/usr/bin/env bash
# Starts Claude Code and the doc MCP server in one go.
# Claude Code spawns doc_server.py over stdio (per mcp.json); doc_server.py
# starts the HTTP server as a side effect. Nothing else to launch.
set -euo pipefail
cd "$(dirname "$0")"

# Give the blocking wait_for_user_message tool room to breathe.
export MCP_TIMEOUT=60000
export MCP_TOOL_TIMEOUT=120000

echo "Once Claude connects, open http://127.0.0.1:8765/ in your browser."

exec claude --mcp-config mcp.json \
  --dangerously-skip-permissions --allowedTools "mcp__docserver__wait_for_user_message,mcp__docserver__send_reply,mcp__docserver__read_document,mcp__docserver__read_section,mcp__docserver__update_section" \
  "$(cat agent_prompt.txt)"
