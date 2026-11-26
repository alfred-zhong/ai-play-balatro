#!/usr/bin/env python3
"""Balatro driver using the game's own scorer (simulate endpoint) for exact evaluation."""
import json, os, sys, time
from api import call

BASE = os.path.dirname(os.path.abspath(__file__))

DECKS = ("RED", "BLUE", "YELLOW", "GREEN", "BLACK", "MAGIC", "NEBULA", "GHOST",
         "ABANDONED", "CHECKERED", "ZODIAC", "PAINTED", "ANAGLYPH", "PLASMA", "ERRATIC")

def log(msg):
    print(msg, flush=True)

def s_():
    r = call("gamestate")
    return r.get("result") or r

def err(r):
    return (r or {}).get("error")

# ------------------------------------------------------------------ queries
def simulate_all(top=10):
    r = call("simulate", top=top)
    if err(r):
        return None, err(r)["message"]
    return r["result"], None

def simulate_one(cards):
    r = call("simulate", cards=list(cards))
    if err(r):
        return None, err(r)["message"]
    return r["result"], None

def need_score(st):
    for b in ("small", "big", "boss"):
        if st["blinds"][b]["status"] == "CURRENT":
            return st["blinds"][b]["score"]
    for b in ("small", "big", "boss"):
        if st["blinds"][b]["status"] == "SELECT":
            return st["blinds"][b]["score"]
    return 0

def current_blind(st):
    for b in ("small", "big", "boss"):
        if st["blinds"][b]["status"] == "CURRENT":
            return b, st["blinds"][b]
    return None, None

# ------------------------------------------------------------------ shop
JOKER_TIER = {
    # crude value tiers for buying decisions
    "j_blueprint": 10, "j_brainstorm": 10, "j_baron": 9, "j_triboulet": 9,
    "j_perkeo": 9, "j_mime": 8, "j_hologram": 8, "j_constellation": 8,
    "j_photograph": 7, "j_hanging_chad": 7, "j_ancient": 7, "j_obelisk": 7,
    "j_steel": 6, "j_abstract": 6, "j_trousers": 6, "j_square": 6,
    "j_blackboard": 6, "j_campfire": 6, "j_madness": 5, "j_riff_raff": 5,
}

PLANET_SAFE = ("c_pluto", "c_mercury", "c_uranus", "c_venus", "c_saturn",
               "c_jupiter", "c_earth", "c_mars", "c_neptune", "c_planet_x",
               "c_ceres", "c_eris")

def use_consumables(st):
    """Use planet cards (and unconditional tarots) to level up poker hands."""
    cons = st.get("consumables") or {}
    cards = cons.get("cards") or []
    if not cards:
        return False
    used = False
    for i, c in enumerate(cards):
        key = c.get("key", "")
        # planets only level up: always worth using
        if key in PLANET_SAFE:
            r = call("use", consumable=i)
            if err(r) is None:
                log(f"    USED {key} ({c.get('label')})")
                return True
            log(f"    use {key} failed: {err(r)['message'][:60]}")
    return used


def handle_shop(st):
    shop = (st.get("shop") or {})
    cards = shop.get("cards") or []
    money = st["money"]
    jok = st["jokers"]
    log(f"    shop: {[(c['key'], c['cost']['buy']) for c in cards]} $={money} "
        f"jok={jok['count']}/{jok['limit']}")
    if jok["count"] < jok["limit"] and money >= 5:
        # prefer higher tier, then cheaper
        cands = [(i, c) for i, c in enumerate(cards) if c["cost"]["buy"] <= money - 2]
        if cands:
            cands.sort(key=lambda t: (-JOKER_TIER.get(t[1]["key"], 2), t[1]["cost"]["buy"]))
            i, c = cands[0]
            r = call("buy", card=i)
            if err(r) is None:
                log(f"    BOUGHT {c['key']} for ${c['cost']['buy']}")
                return True
    return False

def packs_of(st):
    p = st.get("packs")
    if isinstance(p, dict):
        return p.get("cards") or []
    if isinstance(p, list):
        return p
    return []


def handle_packs(st):
    """Buy a booster pack when affordable; the pack then opens and we choose."""
    packs = packs_of(st)
    if not packs:
        return
    money = st["money"]
    log(f"    packs: {[(p.get('key'), p.get('cost', {}).get('buy')) for p in packs]} $={money}")
    for i, p in enumerate(packs):
        price = (p.get("cost") or {}).get("buy", 99)
        if price <= money - 3:
            r = call("buy", card=i)
            if err(r) is None:
                log(f"    BOUGHT PACK {p.get('key')} for ${price}")
                return
            log(f"    pack buy failed: {err(r)['message'][:70]}")
            return

def handle_booster(st):
    """Inside an opened booster: take a Joker/Tarot/Planet if useful, else skip."""
    cards = packs_of(st)
    jok = st.get("jokers") or {"count": 0, "limit": 6}
    cons = st.get("consumables") or {}
    log(f"    booster: {[c['key'] for c in cards]}")
    for i, c in enumerate(cards):
        key = c["key"]
        if key.startswith("j_") and jok["count"] < jok["limit"]:
            r = call("pack", card=i)
            if err(r) is None:
                log(f"    TOOK {key} from pack")
                return
        if (key.startswith("c_") or key.startswith("p_")) and cons.get("count", 0) < cons.get("limit", 2):
            r = call("pack", card=i)
            if err(r) is None:
                log(f"    TOOK {key} from pack")
                return
    r = call("pack", skip=True)
    if err(r):
        log(f"    pack skip failed: {err(r)['message'][:80]}")

# ------------------------------------------------------------------ main
BEST_PATH = os.path.join(BASE, "best.json")

def record_best(ante, note=""):
    try:
        cur = json.load(open(BEST_PATH))
    except Exception:
        cur = {"best_ante": 0}
    if ante > cur.get("best_ante", 0):
        cur = {"best_ante": ante, "note": note, "when": time.strftime("%H:%M:%S")}
        with open(BEST_PATH, "w") as f:
            json.dump(cur, f)
        log(f"    *** NEW BEST: ante {ante} ***")
    return cur


def main(max_turns=2000, deck="BLACK", stake="WHITE"):
    turns = 0
    discards_by_hand = {}
    while turns < max_turns:
        turns += 1
        st = s_()
        if not st or "state" not in st:
            time.sleep(0.3); continue
        state = st["state"]
        r = st.get("round") or {}
        jok = st.get("jokers") or {}
        log(f"[{turns}] {state} ante{st.get('ante_num')} ${st.get('money')} chips={r.get('chips')} "
            f"hands={r.get('hands_left')} disc={r.get('discards_left')} jok={jok.get('count', 0)}")

        if state == "GAME_OVER":
            a = st.get("ante_num") or 0
            log(f"GAME OVER at ante {a}")
            record_best(a)
            call("menu")
            time.sleep(1.2)
            r2 = call("start", deck=deck, stake=stake)
            if err(r2):
                log(f"    restart failed: {err(r2)['message'][:90]}")
            time.sleep(2.0)
            continue
        if st.get("won"):
            log("WON!"); return "won"

        if state == "BLIND_SELECT":
            b = None
            for k in ("small", "big", "boss"):
                if st["blinds"][k]["status"] == "SELECT":
                    b = st["blinds"][k]
            if b:
                log(f"    blind={b['name']} eff={b.get('effect','')} need={b['score']}")
            call("select"); time.sleep(0.35)

        elif state == "SELECTING_HAND":
            d, e = simulate_all()
            if d is None:
                log(f"    simulate failed: {e}"); time.sleep(0.5); continue
            best = d["best"][0]
            target = need_score(st)
            have = r.get("chips") or 0
            rem = target - have
            log(f"    best={best['hand']} {best['chips']}x{best['mult']}={best['score']:.0f} "
                f"cards={best['cards']} need={rem} hands={r['hands_left']} disc={r['discards_left']}")

            # play if we can still reach the target, otherwise discard junk
            hands_left = r.get("hands_left") or 1
            should_discard = (best["score"] * hands_left < rem
                              and (r.get("discards_left") or 0) > 0)

            if should_discard:
                hand_n = len(st["hand"]["cards"])
                limit = st["hand"].get("highlighted_limit", 5)
                keep = set(best["cards"])
                # worth[i] = best score among combos containing card i
                worth = {i: 0.0 for i in range(hand_n)}
                for b in d["best"]:
                    for c in b["cards"]:
                        worth[c] = max(worth[c], b["score"])
                dump = [i for i in range(hand_n) if i not in keep]
                dump.sort(key=lambda i: worth[i])
                dump = dump[:limit]
                # if barely anything to dump, widen: drop the weakest kept cards too
                if len(dump) < limit:
                    extra = sorted(keep, key=lambda i: worth[i])
                    dump += [i for i in extra if i not in dump][: limit - len(dump)]
                if dump:
                    res = call("discard", cards=dump)
                    if err(res) is None:
                        log(f"    discard {dump} (worth {[round(worth[i]) for i in dump]})")
                        time.sleep(0.45)
                        continue
                    log(f"    discard rejected: {err(res)['message'][:70]}")
            res = call("play", cards=sorted(best["cards"]))
            if err(res):
                log(f"    play rejected: {err(res)['message'][:100]}")
            time.sleep(0.55)

        elif state == "ROUND_EVAL":
            call("cash_out"); time.sleep(0.45)

        elif state == "SHOP":
            use_consumables(st)
            st = s_()
            handle_shop(st)
            handle_packs(st)
            call("next_round"); time.sleep(0.45)

        elif state in ("BUFFOON_PACK", "TAROT_PACK", "PLANET_PACK", "SPECTRAL_PACK", "STANDARD_PACK"):
            handle_booster(st)
            time.sleep(0.4)

        elif state == "NEW_ROUND":
            time.sleep(0.25)

        elif state == "MENU":
            call("start", deck=deck, stake=stake); time.sleep(2.0)

        else:
            time.sleep(0.3)
    return "timeout"

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    deck = sys.argv[2] if len(sys.argv) > 2 else "BLACK"
    print(main(n, deck))
