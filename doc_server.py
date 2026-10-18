#!/usr/bin/env python3
"""
doc_server.py - one process, two faces:

  * an MCP server over stdio, spawned by the Claude Code agent (per mcp.json)
  * a local HTTP server (default http://127.0.0.1:8765/) that serves doc.html
    and relays per-section chat between the browser and the agent

stdout is reserved for the MCP protocol. All logging goes to stderr.

Run `python3 doc_server.py --http-only` to preview the page without an agent.

Environment overrides: DOC_PATH (default: doc.html next to this script),
DOC_PORT (default: 8765).
"""

import html
import json
import os
import queue
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DOC_PATH = os.environ.get("DOC_PATH", os.path.join(HERE, "doc.html"))
HTTP_PORT = int(os.environ.get("DOC_PORT", "8765"))

incoming = queue.Queue()   # chat messages from the browser, awaiting the agent
replies = {}               # section id -> [reply text, ...] awaiting the browser
transcripts = {}           # section id -> latest full text-area snapshot
lock = threading.Lock()


def log(msg):
    print(f"[docserver] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------- document I/O

def read_doc():
    with open(DOC_PATH, encoding="utf-8") as f:
        return f.read()


def write_doc(text):
    tmp = DOC_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, DOC_PATH)


def content_pattern(section):
    s = re.escape(section)
    return re.compile(
        r"(<!-- content:%s:start -->)(.*?)(<!-- content:%s:end -->)" % (s, s),
        re.DOTALL,
    )


def get_section_content(doc, section):
    m = content_pattern(section).search(doc)
    return m.group(2).strip() if m else None


def splice_section_content(doc, section, new_html):
    pat = content_pattern(section)
    if not pat.search(doc):
        return None
    return pat.sub(lambda m: m.group(1) + "\n" + new_html.strip() + "\n" + m.group(3), doc)


def embed_transcripts(doc):
    """Write every section's latest chat snapshot into its hidden text area."""
    for section, text in transcripts.items():
        pat = re.compile(
            r'(<textarea class="chatlog" id="log-%s"[^>]*>)(.*?)(</textarea>)'
            % re.escape(section),
            re.DOTALL,
        )
        if pat.search(doc):
            escaped = html.escape(text, quote=False)
            doc = pat.sub(lambda m: m.group(1) + escaped + m.group(3), doc)
    return doc


# ---------------------------------------------------------------- HTTP server

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log("http " + (fmt % args))

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/doc.html"):
            try:
                with open(DOC_PATH, "rb") as f:
                    body = f.read()
            except FileNotFoundError:
                self.send_error(404, "doc.html not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/version":
            try:
                self._json({"v": os.stat(DOC_PATH).st_mtime_ns})
            except FileNotFoundError:
                self._json({"v": 0})
        elif path == "/replies":
            with lock:
                out = {s: msgs for s, msgs in replies.items() if msgs}
                replies.clear()
            self._json(out)
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"ok": False, "error": "bad json"}, 400)
            return
        path = urllib.parse.urlparse(self.path).path
        if path == "/chat":
            section = data.get("section")
            with lock:
                transcripts[section] = data.get("snapshot", "")
            incoming.put({"section": section, "text": data.get("text", "")})
            log(f"chat message queued for section {section}")
            self._json({"ok": True})
        elif path == "/snapshot":
            with lock:
                transcripts[data.get("section")] = data.get("snapshot", "")
            self._json({"ok": True})
        else:
            self.send_error(404)


def start_http():
    srv = ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"serving {DOC_PATH} at http://127.0.0.1:{HTTP_PORT}/")
    return srv


# ----------------------------------------------------------------- MCP tools

def tool_wait_for_user_message(timeout_seconds=45):
    try:
        msg = incoming.get(timeout=max(1, min(int(timeout_seconds), 55)))
        return json.dumps(msg)
    except queue.Empty:
        return json.dumps({"status": "no_messages"})


def tool_send_reply(section, text):
    with lock:
        replies.setdefault(section, []).append(text)
    log(f"reply queued for section {section}")
    return "queued for delivery to the page"


def tool_read_document():
    return read_doc()


def tool_read_section(section):
    content = get_section_content(read_doc(), section)
    if content is None:
        return f"error: no content markers found for section '{section}'"
    return content


def tool_update_section(section, new_content_html):
    doc = read_doc()
    doc = splice_section_content(doc, section, new_content_html)
    if doc is None:
        return f"error: no content markers found for section '{section}'"
    with lock:
        doc = embed_transcripts(doc)
    write_doc(doc)
    log(f"section {section} updated; page will reload")
    return f"section {section} updated in {os.path.basename(DOC_PATH)}; the page will reload itself"


def build_mcp():
    try:  # mcp >= 2.0
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:  # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server

    server = Server("docserver")

    @server.tool()
    def wait_for_user_message(timeout_seconds: int = 45) -> str:
        """Block up to timeout_seconds waiting for the next chat message from the
        page. Returns JSON {"section": ..., "text": ...} or {"status": "no_messages"}
        if the wait timed out. Call this in a loop, forever."""
        return tool_wait_for_user_message(timeout_seconds)

    @server.tool()
    def send_reply(section: str, text: str) -> str:
        """Send a plain-text chat reply that appears in the section's chat text
        area on the page without a reload."""
        return tool_send_reply(section, text)

    @server.tool()
    def read_document() -> str:
        """Return the full current HTML of the document."""
        return tool_read_document()

    @server.tool()
    def read_section(section: str) -> str:
        """Return the current content HTML of one section (what sits between its
        content markers)."""
        return tool_read_section(section)

    @server.tool()
    def update_section(section: str, new_content_html: str) -> str:
        """Replace one section's content in the document file with
        new_content_html (inner HTML only: headings/paragraphs, no <section>
        wrapper, no chat widgets). Chat transcripts for all sections are embedded
        into the regenerated file, and the page reloads itself."""
        return tool_update_section(section, new_content_html)

    return server


if __name__ == "__main__":
    start_http()
    if "--http-only" in sys.argv:
        log("http-only mode; no MCP transport (Ctrl-C to stop)")
        threading.Event().wait()
    else:
        build_mcp().run()  # stdio transport; blocks until the agent disconnects
