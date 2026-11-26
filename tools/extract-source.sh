#!/bin/bash
# Extract Balatro's Lua source for reference.
#
# Balatro ships its Lua unencrypted inside Balatro.love (a zip).
# Reading it is how we learned the exact scoring pipeline
# (see docs/lessons.md). Extract on demand instead of committing ~85MB.
set -eu

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$REPO/.game-source}"
B="${BALATRO_DIR:-$HOME/Library/Application Support/Steam/steamapps/common/Balatro}"
LOVE="$B/Balatro.app/Contents/Resources/Balatro.love"

[ -f "$LOVE" ] || { echo "not found: $LOVE"; echo "set BALATRO_DIR if the game lives elsewhere"; exit 1; }

mkdir -p "$OUT"
unzip -o -q "$LOVE" -d "$OUT"
echo "extracted to $OUT"
echo
echo "useful files:"
echo "  functions/state_events.lua   evaluate_play — the real scoring loop"
echo "  functions/common_events.lua  eval_card — per-card effects"
echo "  functions/misc_functions.lua evaluate_poker_hand, mod_chips/mod_mult"
echo "  card.lua                     Card:get_chip_bonus / calculate_joker"
