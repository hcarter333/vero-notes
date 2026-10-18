# How the vero-notes system operates

One Python process, one Claude Code agent, one HTML file on disk. The user
reads and chats in the browser; the agent lives in the Claude Code CLI.

## Moving parts

```
browser (http://127.0.0.1:8765/)
   | HTTP: GET /, /replies, /version; POST chat messages
   v
doc_server.py  -- single process, two faces:
   |   HTTP server on 127.0.0.1:8765 (serves doc.html, relays chat)
   |   MCP server over stdio (stdout = MCP channel, logs on stderr)
   v
Claude Code agent (spawned claude session with docserver MCP tools)
```

- `doc.html` — the document. Section content sits between
  `<!-- content:sN:start/end -->` markers; each section's chat history is
  embedded in a hidden `<textarea class="chatlog">`.
- `doc_server.py` — started by Claude Code as an MCP server (per
  `mcp.json`); starting the HTTP server on port 8765 is a side effect.
- `start.sh` — launches `claude` with `mcp.json` and the loop prompt from
  `agent_prompt.txt`, pre-allowing the five docserver tools.
- `CLAUDE.md` — same loop instructions, loaded automatically by every
  session started in this directory. This is the safety net: even a bare
  `claude` launch (or a session after /clear) becomes a polling agent.
- `.claude/settings.json` + `.claude/hooks/keep-polling.sh` — a Stop hook.
  When the agent tries to end its turn, the hook curls
  `http://127.0.0.1:8765/version`; if the server answers, it blocks the
  stop and tells the agent to resume polling. Rate-capped (6 blocks per
  10 minutes, stamps in `.claude/hooks/.stop-stamps`) so a broken session
  cannot spin forever. Hooks load at session start, so changes take effect
  on the next `start.sh`.

## Message flow

1. User clicks Discuss on a section, types, clicks Send. The first Send
   after any page load transmits the whole text area (so a fresh agent
   session gets full history); later Sends transmit only new text.
2. The agent sits in a loop on the MCP tool `wait_for_user_message`, which
   blocks until a message arrives (or returns `{"status": "no_messages"}`
   on timeout, and the agent calls it again).
3. The agent answers with `send_reply(section, text)`. The page polls
   `/replies` every 2 s and appends replies to the chat text area — no
   page reload.
4. When the user clearly asks for a document change ("update my doc"), the
   agent calls `update_section(section, new_content_html)`. The server
   splices the new HTML between that section's markers AND embeds every
   section's current chat transcript into its hidden text area, then
   writes doc.html. The page polls `/version` (file mtime) every 3 s and
   reloads itself; open chat boxes and unsent typing are restored from
   sessionStorage.

## MCP tools

- `wait_for_user_message(timeout_seconds)` — block for the next chat
  message; `{"status": "no_messages"}` on timeout.
- `send_reply(section, text)` — queue a plain-text chat reply.
- `read_document()` / `read_section(section)` — inspect current HTML.
- `update_section(section, new_content_html)` — rewrite one section in
  situ (inner HTML only; no section wrapper, markers, or chat widgets).
  The agent never edits doc.html with file tools, or the embedded chat
  histories would be lost.

## Persistence and what can be lost

- Section content: always on disk in doc.html (ordinary git diffs).
- Chat history: on disk only as of the last `update_section`; replies
  since then live in server memory plus the browser text area. Killing
  the server before an update loses the agent-side replies not yet
  embedded (the user side is still in the browser until the tab closes).
  A no-op `update_section` (same content) is a cheap way to checkpoint
  all transcripts before shutting down.

## Failure modes and recovery

- Page loads but chat is dead: the server is probably fine; the agent is
  not polling. Check the CLI. Typing "keep waiting for messages" there
  resumes the loop. The first Send from the page re-transmits full
  history, so nothing is lost. CLAUDE.md plus the Stop hook make this
  rare: new sessions self-start the loop, and running sessions are
  blocked from ending their turn while the server is up.
- Page does not load at all: check the process (`pgrep -af doc_server`)
  and the port (`ss -tlnp | grep 8765`); restart via `start.sh`.
- To shut down cleanly: stop the server (or Ctrl+C the claude session —
  with the server down the Stop hook lets the turn end normally).

## Costs of the polling loop

Each `wait_for_user_message` call is one model turn. The whole
conversation is resent to the API per turn, but prompt caching makes the
unchanged prefix a cheap cache read; an idle poll adds only a few dozen
fresh tokens. Real context growth comes from reading and rewriting
sections, not from waiting.

## Known limits

- One agent serves all five sections serially; per-section subagents are
  the planned next step.
- The Stop hook blocks turn-ending unconditionally while the server runs
  (until the rate cap trips); to end a session deliberately, stop the
  server first or interrupt with Esc/Ctrl+C.
