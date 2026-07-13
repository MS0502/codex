#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

DOWNLOADS="${HOME}/storage/downloads"
TR_DIR="${DOWNLOADS}/TR_KR_LOCAL"
TOKEN="${TR_DIR}/tr_access_token.tmp"
TRACE="${HOME}/MOBOX_TR_STAGE_TRACE_V2.sh"

if [ ! -f "$TRACE" ]; then
  echo "ERROR: trace script not found: $TRACE" >&2
  echo "Download MOBOX_TR_STAGE_TRACE_V2.sh first." >&2
  exit 2
fi

if [ ! -e "$TOKEN" ]; then
  echo "AUTH_TOKEN_MISSING"
  echo "Correct order:"
  echo "1. Open the official TalesRunner site in Chrome and log in."
  echo "2. Press Game Start and wait for the protocol receiver to say it received the request."
  echo "3. Run: python ~/storage/downloads/TR_KR_LOCAL/TR_AUTH_BRIDGE.py"
  echo "4. Run this script again immediately."
  exit 3
fi

if [ ! -s "$TOKEN" ]; then
  echo "AUTH_TOKEN_EMPTY"
  rm -f "$TOKEN"
  echo "The empty token file was removed. Repeat Game Start and TR_AUTH_BRIDGE.py." >&2
  exit 4
fi

size="$(wc -c < "$TOKEN" | tr -d '[:space:]')"
mtime="$(stat -c %Y "$TOKEN" 2>/dev/null || echo 0)"
now="$(date +%s)"
age=$((now - mtime))

case "$size" in
  ''|*[!0-9]*)
    echo "ERROR: could not determine token size" >&2
    exit 5
    ;;
esac

if [ "$size" -lt 20 ]; then
  echo "AUTH_TOKEN_TOO_SHORT size=$size"
  rm -f "$TOKEN"
  echo "The invalid token file was removed. Repeat Game Start and TR_AUTH_BRIDGE.py." >&2
  exit 6
fi

if [ "$age" -lt 0 ]; then age=0; fi

echo "AUTH_TOKEN_READY size=$size age_seconds=$age"
echo "The token content will not be displayed."
echo "Starting sanitized stage trace now."
exec "$TRACE"
