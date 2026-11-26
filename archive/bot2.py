#!/usr/bin/env python3
"""Balatro driver: 5-card exact enumeration + conservative joker model + score calibration."""
import json, os, statistics, sys, time
from itertools import combinations
from api import call

BASE = os.path.dirname(os.path.abspath(__file__))
CALIB_PATH = os.path.join(BASE, "calib.json")

RANK_CHIPS = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":10,"Q":10,"K":10,"A":11}
RANK_ORDER = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}
FACE = {"J","Q","K"}
ODD  = {"A","3","5","7","9"}

# ---------------------------------------------------------------- hand class
def classify5(cards):
    ranks = [c["value"]["rank"] for c in cards]
    suits = [c["value"]["suit"] for c in cards]
    cnt = {}
    for r in ranks: cnt[r] = cnt.get(r, 0) + 1
    counts = sorted(cnt.values(), reverse=True)
    flush = len(set(suits)) == 1
    orders = sorted(RANK_ORDER[r] for r in ranks)
    straight = len(set(orders)) == 5 and (orders[-1] - orders[0] == 4 or orders == [2,3,4,5,14])
    if counts[0] == 5:                                   name = "Flush Five" if flush else "Five of a Kind"
    elif counts[0] == 3 and counts[1] == 2:              name = "Flush House" if flush else "Full House"
    elif straight and flush:                             name = "Straight Flush"
    elif counts[0] == 4:                                 name = "Four of a Kind"
    elif flush:                                          name = "Flush"
    elif straight:                                       name = "Straight"
    elif counts[0] == 3:                                 name = "Three of a Kind"
    elif counts[0] == 2 and counts[1] == 2:              name = "Two Pair"
    elif counts[0] == 2:                                 name = "Pair"
    else:                                                name = "High Card"

    if name in ("Flush","Straight","Straight Flush","Full House","Five of a Kind","Flush House","Flush Five"):
        scoring = list(range(5))
    elif name == "High Card":
        scoring = [max(range(5), key=lambda i: RANK_ORDER[ranks[i]])]
    elif name == "Pair":
        r = max(cnt, key=lambda k: (cnt[k], RANK_ORDER[k]))
        scoring = [i for i in range(5) if ranks[i] == r]
    elif name == "Two Pair":
        prs = [k for k in cnt if cnt[k] == 2]
        scoring = [i for i in range(5) if ranks[i] in prs]
    else:
        t = max(cnt, key=lambda k: (cnt[k], RANK_ORDER[k]))
        scoring = [i for i in range(5) if ranks[i] == t]
    return name, scoring, ranks, suits

HAS_PAIR   = {"Pair","Two Pair","Three of a Kind","Four of a Kind","Full House","Five of a Kind","Flush House","Flush Five"}
HAS_THREE  = {"Three of a Kind","Full House","Five of a Kind","Flush House","Flush Five"}
HAS_FOUR   = {"Four of a Kind","Five of a Kind","Flush Five"}
HAS_STRAIGHT = {"Straight","Straight Flush"}
HAS_FLUSH  = {"Flush","Straight Flush","Flush House","Flush Five"}

# ---------------------------------------------------------------- joker model
def joker_value(j, hn, ranks, suits, scoring, st, hands_left, discards_left):
    """(add_chips, add_mult, xmult) — unknown jokers contribute 0 (conservative)."""
    k = j.get("key", "")
    ac = m = 0.0
    x = 1.0
    sc_r = [ranks[i] for i in scoring]
    sc_s = [suits[i] for i in scoring]
    n_jok = max(1, st.get("jokers", {}).get("count", 1))
    n_disc = discards_left
    money = st.get("money", 0)
    deck_left = st.get("cards", {}).get("count", 0)

    def per_suit(suit, amt):
        return amt * sum(1 for s in sc_s if s == suit)

    if   k == "j_joker":            m += 4
    elif k == "j_greedy_joker":     m += per_suit("D", 3)
    elif k == "j_lusty_joker":      m += per_suit("H", 3)
    elif k == "j_wrathful_joker":   m += per_suit("S", 3)
    elif k == "j_gluttonous_joker": m += per_suit("C", 3)
    elif k == "j_half_joker":       m += 20 if len(scoring) <= 3 else 0
    elif k == "j_banner":           ac += 30 * n_disc
    elif k == "j_abstract":         m += 3 * n_jok
    elif k == "j_smiley":           m += 5
    elif k == "j_blue_joker":       ac += 2 * deck_left
    elif k == "j_ice_cream":        ac += 100
    elif k == "j_green_joker":      m += 1
    elif k == "j_misprint":         m += 10
    elif k == "j_bull":             ac += 2 * money
    elif k == "j_scary_face":       ac += 30 * sum(1 for r in sc_r if r in FACE)
    elif k == "j_odd_todd":         ac += 31 * sum(1 for r in sc_r if r in ODD)
    elif k == "j_scholar":          ac += 20 * sc_r.count("A"); m += 4 * sc_r.count("A")
    elif k == "j_sly":              ac += 50 if hn in HAS_PAIR else 0
    elif k == "j_wily":             ac += 100 if hn in HAS_THREE else 0
    elif k == "j_clever":           ac += 80 if hn == "Two Pair" else 0
    elif k == "j_devious":          ac += 100 if hn in HAS_STRAIGHT else 0
    elif k == "j_crafty":           ac += 80 if hn in HAS_FLUSH else 0
    elif k == "j_duo":              x *= 2 if hn in HAS_PAIR else 1
    elif k == "j_trio":             x *= 3 if hn in HAS_THREE else 1
    elif k == "j_family":           x *= 4 if hn in HAS_FOUR else 1
    elif k == "j_order":            x *= 3 if hn in HAS_STRAIGHT else 1
    elif k == "j_tribe":            x *= 2 if hn in HAS_FLUSH else 1
    return ac, m, x

# ---------------------------------------------------------------- calibration
def load_calib():
    try:
        with open(CALIB_PATH) as f: return json.load(f)
    except Exception:
        return {}

def save_calib(c):
    try:
        with open(CALIB_PATH, "w") as f: json.dump(c, f, indent=1)
    except Exception:
        pass

def calib_for(c, hn, default=1.0):
    v = c.get(hn) or c.get("*")
    return v if v else default

# ---------------------------------------------------------------- evaluation
def evaluate(st, idx, calib):
    hand = st["hand"]["cards"]
    cards = [hand[i] for i in idx]
    hn, scoring, ranks, suits = classify5(cards)
    h = st["hands"][hn]
    chips = h["chips"] + sum(RANK_CHIPS.get(ranks[i], 0) for i in scoring)
    mult = h["mult"]
    for j in st["jokers"].get("cards", []):
        ac, m, x = joker_value(j, hn, ranks, suits, scoring, st,
                               st["round"]["hands_left"], st["round"]["discards_left"])
        chips += ac; mult += m
    raw = chips * mult
    for j in st["jokers"].get("cards", []):
        _, _, x = joker_value(j, hn, ranks, suits, scoring, st,
                              st["round"]["hands_left"], st["round"]["discards_left"])
        raw *= x
    return raw * calib_for(calib, hn), hn, raw

def best_play(st, calib):
    hand = st["hand"]["cards"]
    n = len(hand)
    if n == 0: return None
    size = min(5, n)
    best = None
    for idx in combinations(range(n), size):
        score, hn, raw = evaluate(st, idx, calib)
        if best is None or score > best[0]:
            best = (score, list(idx), hn, raw)
    return best

# ---------------------------------------------------------------- plumbing
def s_():
    r = call("gamestate")
    return r.get("result") or r

def need_score(st):
    for b in ("small", "big", "boss"):
        if st["blinds"][b]["status"] == "CURRENT": return st["blinds"][b]["score"]
    for b in ("small", "big", "boss"):
        if st["blinds"][b]["status"] == "SELECT": return st["blinds"][b]["score"]
    return 0

def log(msg):
    print(msg, flush=True)

# ---------------------------------------------------------------- shop
def shop_buy(st, calib):
    shop = st.get("shop") or {}
    cards = shop.get("cards") or []
    money = st["money"]
    jok = st["jokers"]
    log(f"    shop: {[(c['key'], c['cost']['buy']) for c in cards]} $={money} jok={jok['count']}/{jok['limit']}")
    # buy jokers while slots free, keeping $1
    for i, c in enumerate(cards):
        if jok["count"] >= jok["limit"]:
            break
        price = c["cost"]["buy"]
        if price <= money - 1:
            r = call("buy", card=i)
            if r.get("error") is None:
                money -= price
                jok = (s_()["jokers"])
                log(f"    BOUGHT {c['key']} for ${price}")
    # reroll while rich
    if money >= 20 and jok["count"] < jok["limit"]:
        r = call("reroll")
        if r.get("error") is None:
            log("    reroll")

def shop_packs(st, calib):
    packs = (st.get("shop") or {}).get("booster_cards") or []
    if not packs:
        return
    log(f"    packs: {[(p['key'], p['cost']['buy']) for p in packs]}")

# ---------------------------------------------------------------- main loop
def main(max_turns=600):
    calib = load_calib()
    turns = 0
    last_pred = None
    last_chips = 0
    while turns < max_turns:
        turns += 1
        st = s_()
        state = st["state"]; r = st.get("round", {})
        log(f"[{turns}] {state} ante{st['ante_num']} ${st['money']} chips={r.get('chips')} "
            f"hands={r.get('hands_left')} disc={r.get('discards_left')} jok={st['jokers']['count']}")

        # calibrate from the previous play
        if last_pred and r.get("chips") is not None:
            gained = r["chips"] - last_chips
            if state == "SELECTING_HAND" and gained > 0 and last_pred > 0:
                ratio = gained / last_pred
                hn = last_pred_hand
                cur = calib.get(hn)
                calib[hn] = ratio if cur is None else round(0.5 * cur + 0.5 * ratio, 3)
                save_calib(calib)
                log(f"    calib {hn}: pred={last_pred:.0f} actual={gained} -> {calib[hn]}")
            last_pred = None

        if state == "GAME_OVER":
            log("GAME OVER"); return "over"
        if st.get("won"):
            log("WON!"); return "won"

        if state == "BLIND_SELECT":
            call("select"); time.sleep(0.3)
        elif state == "SELECTING_HAND":
            best = best_play(st, calib)
            if not best:
                time.sleep(0.3); continue
            score, idx, hn, raw = best
            target = need_score(st)
            remaining = target - (r.get("chips") or 0)
            log(f"    best={hn} pred={score:.0f} raw={raw:.0f} cards={idx} need={remaining} "
                f"hands={r['hands_left']} disc={r['discards_left']}")
            if score < remaining and r.get("discards_left", 0) > 0:
                keep = set(idx)
                dump = [i for i in range(len(st["hand"]["cards"])) if i not in keep]
                if dump:
                    res = call("discard", cards=dump[:5])
                    if res.get("error") is None:
                        log(f"    discard {dump[:5]}")
                    time.sleep(0.4)
                    continue
            before = r.get("chips") or 0
            res = call("play", cards=sorted(idx))
            last_pred, last_pred_hand, last_chips = score, hn, before
            time.sleep(0.5)
        elif state == "ROUND_EVAL":
            call("cash_out"); time.sleep(0.4)
        elif state == "SHOP":
            shop_buy(st, calib)
            call("next_round"); time.sleep(0.4)
        elif state in ("BUFFOON_PACK", "TAROT_PACK", "PLANET_PACK", "SPECTRAL_PACK", "STANDARD_PACK"):
            call("pack", skip=True); time.sleep(0.3)
        elif state == "NEW_ROUND":
            time.sleep(0.2)
        elif state == "MENU":
            call("start", deck="BLACK", stake="WHITE"); time.sleep(1.5)
        else:
            time.sleep(0.25)
    return "timeout"

last_pred = None
last_pred_hand = None

if __name__ == "__main__":
    print(main(int(sys.argv[1]) if len(sys.argv) > 1 else 600))
