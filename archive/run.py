import json, time, sys
from itertools import combinations
from api import call

RANK_CHIPS = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":10,"Q":10,"K":10,"A":11}
RANK_ORDER = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}

def chip_of(c):
    return RANK_CHIPS.get(c["value"]["rank"], 0)

def classify(cards, hands_table):
    ranks = [c["value"]["rank"] for c in cards]
    suits = [c["value"]["suit"] for c in cards]
    cnt = {}
    for r in ranks: cnt[r] = cnt.get(r,0)+1
    counts = sorted(cnt.values(), reverse=True)
    is_flush = len(set(suits)) == 1 and len(cards) == 5
    orders = sorted(RANK_ORDER[r] for r in ranks)
    is_straight = len(cards)==5 and len(set(orders))==5 and (orders[-1]-orders[0]==4 or orders==[2,3,4,5,14])
    if len(cards) < 5:
        is_flush = False; is_straight = False
        if len(cards)>=1 and counts[0]==len(cards) and len(cards)>=5: pass
    if counts[0]==5 and is_flush: name="Flush Five"
    elif counts[0]==3 and len(counts)>1 and counts[1]==2 and is_flush: name="Flush House"
    elif counts[0]==5: name="Five of a Kind"
    elif is_straight and is_flush: name="Straight Flush"
    elif counts[0]==4: name="Four of a Kind"
    elif counts[0]==3 and len(counts)>1 and counts[1]==2: name="Full House"
    elif is_flush: name="Flush"
    elif is_straight: name="Straight"
    elif counts[0]==3: name="Three of a Kind"
    elif counts[0]==2 and len(counts)>1 and counts[1]==2: name="Two Pair"
    elif counts[0]==2: name="Pair"
    else: name="High Card"
    if name in ("Flush","Straight","Straight Flush","Full House","Five of a Kind","Flush House","Flush Five"):
        scoring = list(range(len(cards)))
    elif name=="High Card":
        scoring = [max(range(len(cards)), key=lambda i: RANK_ORDER[ranks[i]])]
    elif name=="Pair":
        r = max(cnt, key=lambda k:(cnt[k], RANK_ORDER[k]))
        scoring=[i for i in range(len(cards)) if ranks[i]==r]
    elif name=="Two Pair":
        prs = sorted([k for k in cnt if cnt[k]==2], key=lambda k:RANK_ORDER[k], reverse=True)
        scoring=[i for i in range(len(cards)) if ranks[i] in prs]
    else:
        target = max(cnt, key=lambda k:(cnt[k], RANK_ORDER[k]))
        scoring=[i for i in range(len(cards)) if ranks[i]==target]
    h = hands_table.get(name, {"chips":5,"mult":1})
    chips = h["chips"] + sum(chip_of(cards[i]) for i in scoring)
    return name, chips, h["mult"], scoring

def best_action(state):
    hand = state["hand"]["cards"]
    ht = state["hands"]
    jokers = state["jokers"]["cards"]
    n = len(hand)
    maxsel = state["hand"].get("highlighted_limit", 5)
    best = None
    for k in range(1, min(maxsel, n)+1):
        for idx in combinations(range(n), k):
            cards=[hand[i] for i in idx]
            name, chips, mult, scoring = classify(cards, ht)
            score = chips*mult
            # crude joker contributions
            for j in jokers:
                kk = j.get("key","")
                if kk=="j_joker": score = (chips)*(mult+4)
                elif kk in ("j_duo",) : score*=2
                elif kk in ("j_trio",): score*=3
                elif kk in ("j_banner",): score=(chips+30)*mult
            if best is None or score > best[0]:
                best=(score, list(idx), name, chips, mult)
    return best, hand

def wait_state(targets, timeout=40, interval=0.15):
    t0=time.time()
    while time.time()-t0 < timeout:
        s = call("gamestate")["result"]
        if s["state"] in targets: return s
        time.sleep(interval)
    return call("gamestate")["result"]

def show(s, tag=""):
    r=s["round"]
    print(f"[{tag}] state={s['state']} ante={s['ante_num']} money=${s['money']} "
          f"chips={r['chips']} hands={r['hands_left']} disc={r['discards_left']} "
          f"jokers={s['jokers']['count']}", flush=True)

def need_score(s):
    st=s["state"]
    for b in ("small","big","boss"):
        if s["blinds"][b]["status"]=="SELECT":
            return s["blinds"][b]["score"], b
    # during round: current blind
    for b in ("small","big","boss"):
        if s["blinds"][b]["status"]=="CURRENT":
            return s["blinds"][b]["score"], b
    return None, None

