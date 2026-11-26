import json, time, sys, os
import urllib.request

URL = "http://127.0.0.1:12346"

def call(method, **params):
    payload = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params:
        payload["params"] = params
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def try_call(method, **params):
    try:
        r = call(method, **params)
        if "error" in r:
            return None, r["error"]
        return r.get("result"), None
    except Exception as e:
        return None, str(e)

RANK_CHIPS = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":10,"Q":10,"K":10,"A":11}
RANK_ORDER = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}

def card_chips(c):
    v = RANK_CHIPS.get(c["value"]["rank"], 0)
    for m in (c.get("modifier") or []):
        pass
    return v

def evaluate_five(cards, hands_table):
    """Return (score_chips, mult, hand_name, scoring_cards_indices)"""
    ranks = [c["value"]["rank"] for c in cards]
    suits = [c["value"]["suit"] for c in cards]
    cnt = {}
    for r in ranks:
        cnt[r] = cnt.get(r, 0) + 1
    counts = sorted(cnt.values(), reverse=True)
    is_flush = len(set(suits)) == 1
    # straight
    orders = sorted(RANK_ORDER[r] for r in ranks)
    is_straight = False
    if len(set(orders)) == 5:
        if orders[-1] - orders[0] == 4:
            is_straight = True
        elif orders == [2,3,4,5,14]:  # A-2-3-4-5
            is_straight = True

    if counts[0] == 5 and is_flush: name = "Flush Five"
    elif counts[0] == 3 and counts[1] == 2 and is_flush: name = "Flush House"
    elif counts[0] == 5: name = "Five of a Kind"
    elif is_straight and is_flush: name = "Straight Flush"
    elif counts[0] == 4: name = "Four of a Kind"
    elif counts[0] == 3 and counts[1] == 2: name = "Full House"
    elif is_flush: name = "Flush"
    elif is_straight: name = "Straight"
    elif counts[0] == 3: name = "Three of a Kind"
    elif counts[0] == 2 and counts[1] == 2: name = "Two Pair"
    elif counts[0] == 2: name = "Pair"
    else: name = "High Card"

    # which cards score
    if name in ("Flush","Straight","Straight Flush","Full House","Five of a Kind",
                "Flush House","Flush Five"):
        scoring = list(range(5))
    elif name == "High Card":
        best = max(range(5), key=lambda i: RANK_ORDER[ranks[i]])
        scoring = [best]
    elif name == "Pair":
        r = max(cnt, key=lambda k: (cnt[k], RANK_ORDER[k]))
        scoring = [i for i in range(5) if ranks[i] == r]
    elif name == "Two Pair":
        pairs = sorted([k for k in cnt if cnt[k] == 2], key=lambda k: RANK_ORDER[k], reverse=True)
        scoring = [i for i in range(5) if ranks[i] in pairs]
    elif name == "Three of a Kind":
        r = [k for k in cnt if cnt[k] == 3][0]
        scoring = [i for i in range(5) if ranks[i] == r]
    elif name == "Four of a Kind":
        r = [k for k in cnt if cnt[k] == 4][0]
        scoring = [i for i in range(5) if ranks[i] == r]
    else:
        scoring = list(range(5))

    h = hands_table.get(name, {"chips": 5, "mult": 1})
    chips = h["chips"] + sum(card_chips(cards[i]) for i in scoring)
    mult = h["mult"]
    return chips, mult, name, scoring

JOKER_MULT = {  # flat mult additions when hand scores
    "j_joker": 4,
}
JOKER_CHIPS = {
    "j_banner": 30,
    "j_scary_face": 30,
    "j_abstract": 3,
}
JOKER_XMULT = {
    "j_duo": 2, "j_trio": 3, "j_family": 4, "j_order": 3, "j_tribe": 2,
    "j_cavendish": 3,
}

def joker_bonus(jokers, hand_name, played_rank_counts):
    chips = 0; mult = 0; xmult = 1.0
    for j in jokers:
        k = j.get("key","")
        if k in JOKER_CHIPS: chips += JOKER_CHIPS[k]
        if k in JOKER_MULT: mult += JOKER_MULT[k]
        if k in JOKER_XMULT: xmult *= JOKER_XMULT[k]
    return chips, mult, xmult

def best_play(state):
    hand = state["hand"]["cards"]
    hands_table = state["hands"]
    jokers = state["jokers"]["cards"]
    n = len(hand)
    best = None
    from itertools import combinations
    k = min(5, n)
    for idx in combinations(range(n), k):
        cards = [hand[i] for i in idx]
        chips, mult, name, scoring = evaluate_five(cards, hands_table)
        jc, jm, jx = joker_bonus(jokers, name, None)
        score = (chips + jc) * (mult + jm) * jx
        if best is None or score > best[0]:
            best = (score, list(idx), name, chips, mult)
    return best, hand

def log(msg):
    print(msg, flush=True)
