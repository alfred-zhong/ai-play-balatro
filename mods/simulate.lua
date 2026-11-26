-- src/lua/endpoints/simulate.lua
-- Dry-run scoring. Calls Card methods and Card:calculate_joker directly (avoids
-- eval_card's cardarea identity checks, which don't hold outside a real play).

local ORDER = {
  "Flush Five", "Flush House", "Five of a Kind", "Straight Flush",
  "Four of a Kind", "Full House", "Flush", "Straight",
  "Three of a Kind", "Two Pair", "Pair", "High Card",
}

local ERRORS = {}
local function safe(fn, fallback, tag)
  local ok, res = pcall(fn)
  if ok then return res end
  ERRORS[#ERRORS + 1] = tostring(tag or "?") .. ": " .. tostring(res)
  return fallback
end

local function pick_hand(poker_hands)
  for _, name in ipairs(ORDER) do
    local t = poker_hands[name]
    if t and next(t) then return name, t[1] end
  end
  return "High Card", (poker_hands["High Card"] and poker_hands["High Card"][1]) or {}
end

local function simulate(cards)
  if #cards == 0 then return { score = 0, hand = "None", chips = 0, mult = 0, scoring = 0 } end

  local poker_hands = evaluate_poker_hand(cards)
  local text, scoring_hand = pick_hand(poker_hands)
  scoring_hand = scoring_hand or {}

  local hd = G.GAME.hands[text]
  if not hd then return { score = 0, hand = text, chips = 0, mult = 0, scoring = 0 } end

  local chips = hd.chips + 0.0
  local mult = hd.mult + 0.0
  local DBG = { nscoring = #scoring_hand, base_chips = hd.chips, base_mult = hd.mult, per = {} }

  local saved_dollars = G.GAME.dollars
  local blind = G.GAME.blind
  local saved_trig = blind and blind.triggered

  if blind and not blind.disabled then
    local res = safe(function() return blind:debuff_hand(cards, poker_hands, text) end, false, "debuff")
    blind.triggered = saved_trig
    if res then
      G.GAME.dollars = saved_dollars
      return { score = 0, hand = text, chips = 0, mult = 0, scoring = #scoring_hand, debuffed = true }
    end
    local nm, nc = safe(function()
      return blind:modify_hand(cards, poker_hands, text, mult, chips)
    end, nil, "modify_hand")
    if type(nm) == "number" then mult = nm end
    if type(nc) == "number" then chips = nc end
  end

  local ctx = { full_hand = cards, scoring_hand = scoring_hand, scoring_name = text,
                poker_hands = poker_hands }

  -- 1) scoring cards' own chip/mult, repeated per retrigger (Sock and Buskin,
  --    Hanging Chad, red seals, ...). Mirrors state_events.lua's per-card loop:
  --    a joker watching an individual card returns the plain fields
  --    `chips` / `mult` / `x_mult` (NOT chip_mod/mult_mod/Xmult_mod).
  for i = 1, #scoring_hand do
    local card = scoring_hand[i]
    if not card.debuff then
      local reps = 1
      for k = 1, #G.jokers.cards do
        local jk = G.jokers.cards[k]
        local e = safe(function()
          local c2 = { full_hand = cards, scoring_hand = scoring_hand, scoring_name = text,
                       poker_hands = poker_hands, other_card = card, repetition = true,
                       cardarea = G.play }
          return jk:calculate_joker(c2)
        end, nil, "joker_repetition")
        if e and type(e.repetitions) == "number" and e.repetitions > 1 then
          reps = reps + (e.repetitions - 1)
        end
      end

      -- per-card joker effects, cached once and replayed for each repetition
      local per_card = {}
      for k = 1, #G.jokers.cards do
        local jk = G.jokers.cards[k]
        local e = safe(function()
          local c2 = { full_hand = cards, scoring_hand = scoring_hand, scoring_name = text,
                       poker_hands = poker_hands, other_card = card, individual = true,
                       cardarea = G.play }
          return jk:calculate_joker(c2)
        end, nil, "joker_individual")
        if e then per_card[#per_card + 1] = e end
      end

      for _ = 1, reps do
        local c = safe(function() return card:get_chip_bonus() end, 0, "chip_bonus")
        local m = safe(function() return card:get_chip_mult() end, 0, "chip_mult")
        local x = safe(function() return card:get_chip_x_mult(ctx) end, 0, "chip_x")
        if c and c > 0 then chips = chips + c end
        if m and m > 0 then mult = mult + m end
        if x and x > 0 then mult = mult * x end
        DBG.per[#DBG.per + 1] = { key = safe(function() return card.base.value end, "?"),
                                  chips = c, mult = m, x = x, reps = reps }

        local ed = safe(function() return card:get_edition() end, nil, "card_edition")
        if ed then
          if ed.chip_mod then chips = chips + ed.chip_mod end
          if ed.mult_mod then mult = mult + ed.mult_mod end
          if ed.x_mult_mod then mult = mult * ed.x_mult_mod end
        end

        for _, e in ipairs(per_card) do
          if e.chips then chips = chips + e.chips end
          if e.mult then mult = mult + e.mult end
          if e.x_mult then mult = mult * e.x_mult end
          if e.chip_mod then chips = chips + e.chip_mod end
          if e.mult_mod then mult = mult + e.mult_mod end
          if e.Xmult_mod then mult = mult * e.Xmult_mod end
        end
      end
    end
  end

  -- 2) held-card in-hand effects (incl. retriggers, e.g. Mime)
  local scoring_set = {}
  for i = 1, #scoring_hand do scoring_set[scoring_hand[i]] = true end
  for i = 1, #G.hand.cards do
    local card = G.hand.cards[i]
    if not scoring_set[card] and not card.debuff then
      local reps = 1
      local per_card = {}
      for k = 1, #G.jokers.cards do
        local jk = G.jokers.cards[k]
        local e = safe(function()
          local c2 = { full_hand = cards, scoring_hand = scoring_hand, scoring_name = text,
                       poker_hands = poker_hands, other_card = card, individual = true,
                       cardarea = G.hand }
          return jk:calculate_joker(c2)
        end, nil, "joker_held")
        if e then
          if type(e.repetitions) == "number" and e.repetitions > 1 then
            reps = reps + (e.repetitions - 1)
          end
          if e.h_mult or e.x_mult then per_card[#per_card + 1] = e end
        end
      end
      for _ = 1, reps do
        local hm = safe(function() return card:get_chip_h_mult() end, 0, "h_mult")
        local hx = safe(function() return card:get_chip_h_x_mult() end, 0, "h_x")
        if hm and hm > 0 then mult = mult + hm end
        if hx and hx > 0 then mult = mult * hx end
        for _, e in ipairs(per_card) do
          if e.h_mult then mult = mult + e.h_mult end
          if e.x_mult then mult = mult * e.x_mult end
        end
      end
    end
  end

  -- 3) joker main effects (incl. the joker's own edition bonus)
  for i = 1, #G.jokers.cards do
    local jk = G.jokers.cards[i]
    local e = safe(function()
      local c2 = { full_hand = cards, scoring_hand = scoring_hand, scoring_name = text,
                   poker_hands = poker_hands, joker_main = true, cardarea = G.jokers }
      return jk:calculate_joker(c2)
    end, nil, "joker_main")
    if e then
      if e.chip_mod then chips = chips + e.chip_mod end
      if e.mult_mod then mult = mult + e.mult_mod end
      if e.Xmult_mod then mult = mult * e.Xmult_mod end
      DBG.per[#DBG.per + 1] = { joker = safe(function() return jk.config.center.key end, "?"),
                                chips = e.chip_mod, mult = e.mult_mod, x = e.Xmult_mod }
    end
    local jed = safe(function() return jk:get_edition() end, nil, "joker_edition")
    if jed then
      if jed.chip_mod then chips = chips + jed.chip_mod end
      if jed.mult_mod then mult = mult + jed.mult_mod end
      if jed.x_mult_mod then mult = mult * jed.x_mult_mod end
    end
    -- joker-on-joker
    for _, v in ipairs(G.jokers.cards) do
      local eff = safe(function()
        local c2 = { full_hand = cards, scoring_hand = scoring_hand, scoring_name = text,
                     poker_hands = poker_hands, other_joker = jk }
        return v:calculate_joker(c2)
      end, nil, "joker_on_joker")
      if eff then
        if eff.chip_mod then chips = chips + eff.chip_mod end
        if eff.mult_mod then mult = mult + eff.mult_mod end
        if eff.Xmult_mod then mult = mult * eff.Xmult_mod end
      end
    end
  end

  -- 4) deck/back final step
  if G.GAME.selected_back then
    local nc, nm = safe(function()
      return G.GAME.selected_back:trigger_effect({ context = 'final_scoring_step',
        chips = chips, mult = mult })
    end, nil, "selected_back")
    if type(nc) == "number" then chips = nc end
    if type(nm) == "number" then mult = nm end
  end

  G.GAME.dollars = saved_dollars

  return { score = chips * mult, hand = text, chips = chips, mult = mult,
           scoring = #scoring_hand, dbg = DBG }
end

local function combos(n, k, cb)
  local idx = {}
  local function rec(start, depth)
    if depth > k then cb(idx) return end
    for i = start, n - (k - depth) do
      idx[depth] = i
      rec(i + 1, depth + 1)
    end
  end
  rec(1, 1)
end

return {
  name = "simulate",
  description = "Dry-run scoring of hand combinations via Card:calculate_joker",
  schema = {
    cards = { type = "array", items = "integer", required = false,
      description = "0-based hand card indices; if omitted, all 5-card combos are ranked" },
    top = { type = "integer", required = false, description = "how many top results (default 12)" },
  },
  requires_state = { G.STATES.SELECTING_HAND },

  execute = function(args, send_response)
    local hand = G.hand.cards
    local n = #hand
    if n == 0 then
      send_response({ message = "no cards in hand" })
      return
    end

    if args.cards and #args.cards > 0 then
      local sel = {}
      for _, i in ipairs(args.cards) do sel[#sel + 1] = hand[i + 1] end
      local r = simulate(sel)
      r.cards = args.cards
      r.errors = ERRORS
      send_response(r)
      return
    end

    local k = math.min(5, n)
    local results = {}
    local freq = {}
    for i = 1, n do freq[i] = 0 end

    -- Rank every subset size, not just 5-card plays: hand-retention jokers
    -- (Baron, Shoot the Moon, Raised Fist) make small plays strictly better.
    for size = 1, k do
      combos(n, size, function(idx)
        local sel = {}
        for d = 1, #idx do sel[d] = hand[idx[d]] end
        local r = simulate(sel)
        local ids = {}
        for d = 1, #idx do ids[d] = idx[d] - 1 end
        results[#results + 1] = { cards = ids, score = r.score, hand = r.hand,
          chips = r.chips, mult = r.mult, nscoring = r.scoring, debuffed = r.debuffed }
      end)
    end

    table.sort(results, function(a, b) return a.score > b.score end)

    local topn = args.top or 12
    for i = 1, math.min(topn, #results) do
      for _, c in ipairs(results[i].cards) do freq[c + 1] = freq[c + 1] + 1 end
    end

    local card_freq = {}
    for i = 1, n do
      card_freq[i] = { index = i - 1, freq = freq[i] }
    end

    local out = {}
    for i = 1, math.min(topn, #results) do out[i] = results[i] end
    send_response({ combos = #results, n = n, k = k, best = out,
                   card_freq = card_freq, errors = ERRORS })
  end,
}
