#!/usr/bin/env python3
"""Mechanical toolbox for Balatro. No strategy here — only state, exact scoring, and actions.

Usage:
  ./mech.py status              compact one-screen state
  ./mech.py sim [top]           exact scores for every 5-card combo (game's own scorer)
  ./mech.py play 1,2,3,4,5      play those 0-based hand indices
  ./mech.py discard 0,1,2       discard those 0-based hand indices
  ./mech.py select              select current blind
  ./mech.py skip                skip current blind (for tags)
  ./mech.py buy N               buy shop card index N
  ./mech.py buy pack N          buy booster pack index N
  ./mech.py buy voucher N       buy voucher index N
  ./mech.py use N [targets]     use consumable N, optional 0-based hand targets
  ./mech.py sell N              sell joker N
  ./mech.py pack N | pack skip  take card N from opened booster, or skip
  ./mech.py rearrange 1,0,2,3   reorder jokers (+mult left, xmult right)
  ./mech.py reroll              reroll shop
  ./mech.py next                leave shop / continue
  ./mech.py cashout             collect round rewards
  ./mech.py menu                return to main menu (needed before start)
  ./mech.py start DECK [STAKE]  start a new run
  ./mech.py wait STATE...       block until one of those states
  ./mech.py raw                 full raw gamestate json
"""
import json, sys, time, urllib.request

URL = "http://127.0.0.1:12346"

def call(method, **params):
    payload = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params:
        payload["params"] = params
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": {"message": str(e)}}

def st():
    r = call("gamestate")
    return r.get("result") or {"_error": (r.get("error") or {}).get("message", "no gamestate")}

def wait_for(states, timeout=25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = st()
        if s.get("state") in states:
            return s
        time.sleep(0.15)
    return st()

def cmds(v):
    return [int(x) for x in v.split(",") if x.strip() != ""]

# ---------------------------------------------------------------- formatting
def card(c):
    v = c.get("value") or {}
    r, s = v.get("rank", "?"), v.get("suit", "?")
    mod = c.get("modifier") or {}
    extra = []
    if isinstance(mod, dict):
        if mod.get("enhancement"): extra.append(mod["enhancement"])
        if mod.get("edition"): extra.append(mod["edition"] + "!")
        if mod.get("seal"): extra.append("seal:" + mod["seal"])
    return f"{r}{s}" + (f"[{'/'.join(extra)}]" if extra else "")

def status():
    s = st()
    if "state" not in s:
        print(json.dumps(s)); return
    out = []
    r = s.get("round") or {}
    out.append(f"state={s['state']} ante={s.get('ante_num')} money=${s.get('money')} "
               f"chips={r.get('chips')} hands={r.get('hands_left')} discards={r.get('discards_left')}")
    bl = s.get("blinds") or {}
    cur = None
    for k in ("small", "big", "boss"):
        b = bl.get(k) or {}
        if b.get("status") in ("CURRENT", "SELECT"):
            cur = b
            out.append(f"blind[{k}]={b.get('name')} need={b.get('score')} "
                       f"effect={(b.get('effect') or '').strip() or '-'}")
    jk = (s.get("jokers") or {}).get("cards") or []
    out.append(f"jokers {len(jk)}/{(s.get('jokers') or {}).get('limit')}: " +
               " | ".join(f"{j.get('key')}:{(j.get('value') or {}).get('effect','')}" for j in jk))
    cons = (s.get("consumables") or {}).get("cards") or []
    if cons:
        out.append(f"consumables {len(cons)}/{(s.get('consumables') or {}).get('limit')}: " +
                   " | ".join(f"[{i}]{c.get('key')}" for i, c in enumerate(cons)))
    hand = (s.get("hand") or {}).get("cards") or []
    if hand:
        out.append("hand: " + " ".join(f"[{i}]{card(c)}" for i, c in enumerate(hand)))
    if s.get("state") == "SHOP":
        shop = (s.get("shop") or {}).get("cards") or []
        if shop:
            out.append("shop: " + " | ".join(
                f"[{i}]{c.get('key')} ${(c.get('cost') or {}).get('buy')} "
                f"{(c.get('value') or {}).get('effect','')[:70]}" for i, c in enumerate(shop)))
        packs = (s.get("packs") or {}).get("cards") or []
        if packs:
            out.append("packs: " + " | ".join(
                f"[{i}]{c.get('label')} ${(c.get('cost') or {}).get('buy')} "
                f"{(c.get('value') or {}).get('effect','')[:50]}" for i, c in enumerate(packs)))
    state_now = s.get("state") or ""
    if "BOOSTER_OPENED" in state_now or state_now in (
            "BUFFOON_PACK", "TAROT_PACK", "PLANET_PACK", "SPECTRAL_PACK", "STANDARD_PACK"):
        cards = (s.get("packs") or {}).get("cards") or []
        if cards:
            out.append(">>> BOOSTER OPEN — use 'pack N' to take, 'pack skip' to skip")
            out.append("pack contents: " + " | ".join(
                f"[{i}]{c.get('key')} {(c.get('value') or {}).get('effect','')[:90]}"
                for i, c in enumerate(cards)))
        else:
            out.append(">>> BOOSTER OPEN but no cards listed")
    hands = s.get("hands") or {}
    lv = [f"{k}=Lv{v['level']}({v['chips']}x{v['mult']})" for k, v in hands.items()
          if isinstance(v, dict) and v.get("level", 1) > 1]
    if lv:
        out.append("leveled hands: " + " ".join(lv))
    out.append(f"won={s.get('won')} seed={s.get('seed')}")
    print("\n".join(out))

def sim(top):
    r = call("simulate", top=top)
    if r.get("error"):
        print("ERR " + (r["error"].get("message") or "")[:200]); return
    d = r["result"]
    if d.get("errors"):
        print("warn:", d["errors"][:2])
    for b in d.get("best", []):
        print(f"{b['score']:>8.0f}  {b['hand']:<16} {b['chips']:.0f}x{b['mult']:.1f} "
              f"cards={b['cards']}")
    freq = {c["index"]: c["freq"] for c in d.get("card_freq", [])}
    print("in_top_combos:", freq)

# ---------------------------------------------------------------- actions
def act(method, wait_state=None, **params):
    r = call(method, **params)
    if r.get("error"):
        print("ERR " + (r["error"].get("message") or "")[:220])
        return
    if wait_state:
        s = wait_for(wait_state)
    else:
        time.sleep(0.35)
        s = st()
    print(f"OK {method} -> {s.get('state')} chips={(s.get('round') or {}).get('chips')} "
          f"hands={(s.get('round') or {}).get('hands_left')} "
          f"disc={(s.get('round') or {}).get('discards_left')} money=${s.get('money')}")

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    c = sys.argv[1]
    if c == "status":
        status()
    elif c == "sim":
        sim(int(sys.argv[2]) if len(sys.argv) > 2 else 8)
    elif c == "look":
        s = st()
        if s.get("state") == "SELECTING_HAND":
            r = call("simulate", top=int(sys.argv[2]) if len(sys.argv) > 2 else 6)
            print("----- STATE -----")
            status()
            if r.get("error"):
                print("SIM ERR " + (r["error"].get("message") or "")[:160])
            else:
                d = r["result"]
                print("----- BEST COMBOS (exact, game scorer) -----")
                for b in d.get("best", [])[:6]:
                    print(f"{b['score']:>8.0f}  {b['hand']:<16} {b['chips']:.0f}x{b['mult']:.1f} cards={b['cards']}")
                print("in_top_combos:", {c["index"]: c["freq"] for c in d.get("card_freq", [])})
        else:
            status()
    elif c == "raw":
        print(json.dumps(st(), ensure_ascii=False))
    elif c == "play":
        act("play", cards=cmds(sys.argv[2]))
    elif c == "discard":
        act("discard", cards=cmds(sys.argv[2]))
    elif c == "select":
        act("select", wait_state={"SELECTING_HAND"})
    elif c == "skip":
        act("skip")
    elif c == "buy":
        if len(sys.argv) > 3:
            kind = sys.argv[2]
            if kind == "pack":
                act("buy", pack=int(sys.argv[3]))
            elif kind == "voucher":
                act("buy", voucher=int(sys.argv[3]))
            elif kind == "card":
                act("buy", card=int(sys.argv[3]))
            else:
                print("buy: use 'buy N' or 'buy pack|voucher|card N'")
        else:
            act("buy", card=int(sys.argv[2]))
    elif c == "use":
        if len(sys.argv) > 3:
            act("use", consumable=int(sys.argv[2]), cards=cmds(sys.argv[3]))
        else:
            act("use", consumable=int(sys.argv[2]))
    elif c == "sell":
        act("sell", joker=int(sys.argv[2]))
    elif c == "pack":
        if sys.argv[2] == "skip":
            act("pack", skip=True)
        else:
            act("pack", card=int(sys.argv[2]))
    elif c == "rearrange":
        # rearrange jokers 1,0,2,3  -> reorder joker slots
        act("rearrange", jokers=cmds(sys.argv[2]))
    elif c == "reroll":
        act("reroll")
    elif c == "next":
        act("next_round", wait_state={"BLIND_SELECT", "SELECTING_HAND", "SHOP", "GAME_OVER"})
    elif c == "cashout":
        act("cash_out", wait_state={"SHOP", "GAME_OVER"})
    elif c == "menu":
        act("menu")
    elif c == "start":
        deck = sys.argv[2] if len(sys.argv) > 2 else "BLACK"
        stake = sys.argv[3] if len(sys.argv) > 3 else "WHITE"
        s = st()
        if s.get("state") != "MENU":
            r = call("menu")
            if r.get("error"):
                print("ERR menu: " + (r["error"].get("message") or "")[:150])
            time.sleep(1.2)
        act("start", deck=deck, stake=stake)
    elif c == "wait":
        s = wait_for(set(sys.argv[2:]))
        print(f"state={s.get('state')}")
    else:
        print("unknown command: " + c); print(__doc__)

if __name__ == "__main__":
    main()
