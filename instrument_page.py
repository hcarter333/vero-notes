#!/usr/bin/env python3
"""instrument_page.py - add pagechat Discuss buttons to a findings page.

Give every <div class="finding ..."> block in a findings-style HTML page its
own per-section chat, wired for doc_server.py:

  * the div gains the doc-section class and a stable section id
  * <!-- content:ID:start/end --> markers wrap the finding's content, so
    update_section rewrites the finding without touching the chat widget
  * a Discuss button + hidden chat textarea is appended inside the div
  * the chat CSS is added to the page's stylesheet (uses the page's theme
    variables, with fallbacks, so it follows the dark/light toggle)
  * the generic chat <script> is copied verbatim out of doc.html

Section ids: a finding div that already has an id="..." keeps it. Otherwise
the id comes from the HTML comment that labels the finding, slugging the
part before any colon: <!-- HOOK: WESTERN APPROACHES --> -> "hook",
<!-- WEST HARTLEPOOL CLUSTER --> -> "west-hartlepool-cluster". A finding
with neither gets f-<position>. Ids are permanent once chat history
exists, so rerun output should be reviewed before serving.

Usage:
    python3 instrument_page.py TARGET.html [--doc /path/to/doc.html]

doc.html defaults to the copy next to this script (the chat JS is extracted
from it). The target is modified in place; a TARGET.html.bak backup is left
beside it. Refuses to run on a page that already has content markers.

Serve the result with:
    DOC_PATH=/abs/path/TARGET.html ./start.sh
"""
import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

WIDGET = """<!-- content:{sid}:end -->
  <div class="discuss">
    <button class="discuss-btn" data-section="{sid}">Discuss</button><span class="status" id="status-{sid}"></span>
    <div class="chatbox" hidden id="box-{sid}">
      <textarea class="chatlog" id="log-{sid}" data-section="{sid}" placeholder="Comments, questions, or change requests for this finding..."></textarea>
      <button class="send-btn" data-section="{sid}">Send</button>
    </div>
  </div>
  """

CSS = """
/* ─── per-finding discuss chat (pagechat instrument_page.py) ─── */
.finding .discuss { margin-top: 0.9rem; }
.discuss-btn, .send-btn {
  font: inherit; font-size: 0.78rem; padding: 0.25rem 0.9rem; cursor: pointer;
  background: var(--surface-alt, #eee); color: var(--text, #222);
  border: 1px solid var(--border, #aaa); border-radius: 3px;
}
.discuss-btn:hover, .send-btn:hover { background: var(--border-faint, #ddd); }
.chatbox { margin-top: 0.6rem; }
.chatbox textarea {
  width: 100%; min-height: 9rem; font: 0.78rem/1.45 'Courier New', monospace;
  padding: 0.5rem; box-sizing: border-box;
  background: var(--surface, #fff); color: var(--text, #222);
  border: 1px solid var(--border, #aaa);
}
.send-btn { margin-top: 0.3rem; }
.status { font-size: 0.72rem; color: var(--text-faint, #777); margin-left: 0.6rem; }
"""

DIV_TOKEN = re.compile(r"<div\b|</div>")
FINDING_OPEN = re.compile(r'<div class="finding((?: [a-z-]+)*)"(?: id="([^"]*)")?>')
# an HTML comment with nothing but whitespace between it and the finding div
COMMENT_BEFORE = re.compile(r"<!--\s*([^\n]+?)\s*-->\s*\Z")


def find_close(doc, i):
    """Offset of the </div> matching the <div ...> that ends at i."""
    depth = 1
    for t in DIV_TOKEN.finditer(doc, i):
        depth += 1 if t.group().startswith("<div") else -1
        if depth == 0:
            return t.start()
    sys.exit("error: unbalanced <div>s after a finding block")


def section_id(doc, div_start, index, used):
    """Slug of the comment labelling the finding (its text before any colon)."""
    m = COMMENT_BEFORE.search(doc, 0, div_start)
    words = re.findall(r"[a-z0-9]+", m.group(1).split(":")[0].lower()) if m else []
    sid = "-".join(words) if words else f"f-{index}"
    base, n = sid, 2
    while sid in used:
        sid = f"{base}-{n}"
        n += 1
    used.add(sid)
    return sid


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target", help="findings HTML page to instrument in place")
    ap.add_argument("--doc", default=os.path.join(HERE, "doc.html"),
                    help="doc.html to copy the chat <script> from (default: next to this script)")
    args = ap.parse_args()

    with open(args.target, encoding="utf-8") as f:
        doc = f.read()
    if "<!-- content:" in doc:
        sys.exit(f"error: {args.target} already contains content markers; refusing to double-instrument")
    if "</style>" not in doc or "</body>" not in doc:
        sys.exit("error: target does not look like a full HTML page (missing </style> or </body>)")

    with open(args.doc, encoding="utf-8") as f:
        dochtml = f.read()
    js = re.search(r"<script>\n(\(function \(\) \{.*?)</script>", dochtml, re.S)
    if not js:
        sys.exit(f"error: could not find the chat script in {args.doc}")

    parts, pos, ids = [], 0, []
    used = set(re.findall(r'id="([^"]+)"', doc))  # don't collide with existing ids
    for m in FINDING_OPEN.finditer(doc):
        if m.start() < pos:
            continue  # nested inside a finding we already handled
        close = find_close(doc, m.end())
        inner = doc[m.end():close]
        if m.group(2):
            sid = m.group(2)  # div's own id, already unique in the page
        else:
            sid = section_id(doc, m.start(), len(ids) + 1, used)
        ids.append(sid)
        opening = f'<div class="finding{m.group(1)} doc-section" id="{sid}">\n  <!-- content:{sid}:start -->'
        parts.append(doc[pos:m.start()])
        parts.append(opening + inner + WIDGET.format(sid=sid) + "</div>")
        pos = close + len("</div>")
    if not ids:
        sys.exit('error: no <div class="finding ..."> blocks found in the target')
    parts.append(doc[pos:])
    doc = "".join(parts)

    i = doc.index("</style>")
    doc = doc[:i] + CSS + doc[i:]
    i = doc.index("</body>")
    doc = doc[:i] + "<script>\n" + js.group(1) + "</script>\n\n" + doc[i:]

    shutil.copy2(args.target, args.target + ".bak")
    tmp = args.target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(doc)
    os.replace(tmp, args.target)

    print(f"instrumented {len(ids)} findings in {args.target}:")
    for sid in ids:
        print(f"  {sid}")
    print(f"backup: {args.target}.bak")
    print(f'serve with: DOC_PATH="{os.path.abspath(args.target)}" ./start.sh')


if __name__ == "__main__":
    main()
