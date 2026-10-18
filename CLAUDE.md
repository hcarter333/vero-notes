# vero-notes agent

If this session has the `mcp__docserver__*` tools, you are the live agent
behind the interactive document served at http://127.0.0.1:8765/ (the file
named by DOC_PATH; doc.html by default). Enter the polling loop immediately — even if the user's
first message is about something else, finish answering it and then start
the loop.

The loop:

1. Call `wait_for_user_message`. If it returns `{"status": "no_messages"}`,
   call it again immediately. Never end your turn to wait.
2. A real message contains a section id and text. The text may be the
   section's entire chat history (lines prefixed USER:/CLAUDE: or unprefixed
   user typing) because the page sends the full text area on the first Send
   of a session. Use it as context; respond to the newest request in it.
3. Call `read_section` with the section id before answering questions
   about, or proposing changes to, that section's content.
4. Reply with `send_reply(section, text)`. Plain text only, no markdown.
   Keep replies concise; they appear inside a chat text area on the page.
5. Only when the user says "update my doc" or otherwise clearly asks you to
   apply the change: call `update_section(section, new_content_html)` with
   the complete replacement inner HTML for that section (e.g. an `<h2>` and
   `<p>` elements; no `<section>` wrapper, no chat widgets, no marker
   comments). Then `send_reply` a short confirmation and return to step 1.

Never edit the document file with file tools; always go through `update_section` so
chat histories are preserved in the regenerated file. Do not exit the loop
while the doc server is running.

If this session does NOT have the `mcp__docserver__*` tools, none of the
above applies — this is then an ordinary coding session on the vero-notes
project files.
