# vero-notes

Margin notes that talk back — and tell the truth.

In 1957, Varo Manufacturing of Garland, Texas mimeographed an annotated copy
of Morris K. Jessup's *The Case for the UFO* for the Office of Naval
Research: a book whose margins a pseudonymous reader had filled with
fabricated "insider" commentary, retypeset with the marginal conversation
embedded in the text. vero-notes is the mirror image of the Varo Edition —
flip one letter and the margins tell the truth (*vero*: true).

Concretely: a local HTML document you read in the browser, with a Discuss
button per section. Chat about one section at a time with a Claude Code
agent; say "update my doc" and the agent rewrites that section in place, the
page reloads itself, and your chat history survives inside the regenerated
file. Single server, single CLI agent, everything on local disk.

## Files

- `doc_server.py` - one process: MCP server over stdio (spawned by Claude
  Code) plus an HTTP server on 127.0.0.1:8765 that serves the page and
  relays chat. stdout is the MCP channel; logs go to stderr.
- `mcp.json` - tells Claude Code how to spawn the server.
- `agent_prompt.txt` - the loop the agent runs (wait, reply, update).
- `start.sh` - the one-command launcher.
- `instrument_page.py` - add a Discuss chat to every `<div class="finding">`
  block of a findings-style page (markers, widgets, CSS, chat script), so it
  can be served via `DOC_PATH=/abs/path/page.html ./start.sh`.

No sample document ships in this repo. The served document is any HTML page
whose section content sits between `<!-- content:sN:start/end -->` markers,
with chat history in each section's hidden `<textarea class="chatlog">`;
`instrument_page.py` adds all of that to an existing page.

## Prerequisites

    pip install mcp

(Works with mcp 1.x or 2.x; the server tries the 2.x `MCPServer` import
first and falls back to 1.x `FastMCP`.) Claude Code must be on PATH.

## Run

Instrument a page (adds a "Discuss" chat button to every section, with section ids
taken from the `<!-- COMMENT -->` labelling each one), then serve it:

    python3 instrument_page.py /path/to/page.html
    DOC_PATH=/abs/path/page.html ./start.sh

Then open http://127.0.0.1:8765/ in the browser. From WSL2, the Windows
browser reaches that address directly via localhost forwarding.

(Without `DOC_PATH`, the server looks for `doc.html` next to
`doc_server.py`.)

To preview or restyle the page with no agent attached:

    DOC_PATH=/abs/path/page.html python3 doc_server.py --http-only

## Flow

1. Click "Discuss" on a section (label becomes Chat), type, click Send.
   The first Send after any page load transmits the whole text area, in
   case a fresh agent session is attached; later Sends transmit only the
   new text.  

<img width="736" height="313" alt="image" src="https://github.com/user-attachments/assets/d48c8216-2f05-47c9-bca7-bd60457b64c7" />  

   
3. The agent's replies stream back into the text area (page polls
   /replies every 2 s; no reload).
4. Say "update my doc" in the chat. The agent calls `update_section`,
   which splices new HTML between that section's markers and embeds every
   section's chat transcript into its hidden text area. The page polls
   /version (file mtime) every 3 s and reloads when it changes; open chat
   boxes and unsent typing are restored via sessionStorage.

<img width="741" height="810" alt="image" src="https://github.com/user-attachments/assets/d4340ca9-5862-47ec-a2f5-b1ead93a1269" />


## MCP tools exposed to the agent

- `wait_for_user_message(timeout_seconds)` - blocks until a chat message
  arrives; returns `{"status": "no_messages"}` on timeout so the agent
  can loop.
- `send_reply(section, text)` - queue a chat reply for the page.
- `read_document()` / `read_section(section)` - inspect current HTML.
- `update_section(section, new_content_html)` - rewrite one section in
  situ.

## Known limits

- If the agent doesn't repond in the paage, go to the agent running in the console where you started it and ask it to start the messaging loop.
- If the agent eventually stops polling (long idle, turn limits), type
  "keep waiting for messages" into the Claude Code CLI to resume; the
  first Send from the page re-transmits full history, so nothing is lost.
- Chat transcripts live in server memory between file writes; killing the
  server before an update discards replies not yet embedded in the
  document (the user side of the history is still in the browser text
  area).
- One agent serves all sections serially; per-section subagents are the
  planned next step.

## Development

Tests live in `tests/` (empty for now). CI runs pytest whenever a Python
file changes:

    pip install pytest
    pytest tests
