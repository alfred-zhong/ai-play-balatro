#!/bin/bash
# Robust Balatro restart with retries against port races.
set -u
# Resolve repo root regardless of where this is called from
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="${BALATRO_LOG_DIR:-$REPO/logs}"
B="${BALATRO_DIR:-$HOME/Library/Application Support/Steam/steamapps/common/Balatro}"
NAME="${1:-game}"
mkdir -p "$LOGDIR"
LOG="$LOGDIR/$NAME.log"

port_free() {
  ! lsof -nP -iTCP:12346 -sTCP:LISTEN >/dev/null 2>&1 \
    && ! netstat -an -p tcp 2>/dev/null | grep -q "127.0.0.1.12346"
}

pkill -9 -f "Balatro.app/Contents/MacOS/love" 2>/dev/null
pkill -9 -f "run_lovely_macos.sh" 2>/dev/null

for i in $(seq 1 40); do
  port_free && break
  PID=$(lsof -nP -iTCP:12346 -sTCP:LISTEN -t 2>/dev/null | head -1)
  [ -n "${PID:-}" ] && kill -9 "$PID" 2>/dev/null
  sleep 1
done

port_free || { echo "PORT_STUCK"; exit 4; }

for attempt in 1 2 3; do
  cd "$B" || exit 1
  BALATROBOT_FAST=${BALATROBOT_FAST:-0} BALATROBOT_GAMESPEED=4 BALATROBOT_AUDIO=0 ./run_lovely_macos.sh > "$LOG" 2>&1 &

  for i in $(seq 1 50); do
    if grep -q "HTTP server listening" "$LOG" 2>/dev/null; then
      for k in 1 2 3 4 5 6 7 8; do
        if curl -s -m 2 -X POST http://127.0.0.1:12346 -H "Content-Type: application/json" \
             -d '{"jsonrpc":"2.0","method":"health","id":1}' 2>/dev/null | grep -q '"ok"'; then
          echo "READY"; exit 0
        fi
        sleep 1
      done
    fi
    if grep -q "Failed to bind" "$LOG" 2>/dev/null; then
      pkill -9 -f "Balatro.app/Contents/MacOS/love" 2>/dev/null
      for j in $(seq 1 20); do port_free && break; sleep 1; done
      break
    fi
    sleep 1
  done
done

echo "FAILED"; exit 3
