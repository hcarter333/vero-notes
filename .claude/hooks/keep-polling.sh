#!/usr/bin/env bash
# Stop hook for the vero-notes agent: while the doc server is up, block the
# agent from ending its turn and tell it to resume the polling loop.
# Rate-capped so a misbehaving session can't spin: more than 6 blocks in
# 10 minutes lets the stop through.

STAMPS="$(dirname "$0")/.stop-stamps"
now=$(date +%s)

# Server not running -> allow the stop.
curl -s -m 2 -o /dev/null http://127.0.0.1:8765/version || exit 0

recent=0
if [ -f "$STAMPS" ]; then
  while read -r t; do
    [ $((now - t)) -lt 600 ] && recent=$((recent + 1))
  done < "$STAMPS"
fi
if [ "$recent" -ge 6 ]; then
  exit 0
fi

{ [ -f "$STAMPS" ] && awk -v now="$now" 'now - $1 < 600' "$STAMPS"; echo "$now"; } > "$STAMPS.new" \
  && mv "$STAMPS.new" "$STAMPS"

cat <<'EOF'
{"decision":"block","reason":"The doc server at 127.0.0.1:8765 is still running. Resume the page-chat loop: call mcp__docserver__wait_for_user_message and keep serving section chats as described in CLAUDE.md. Do not end the turn while the server is up."}
EOF
exit 0
