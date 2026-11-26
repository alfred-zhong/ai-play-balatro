import json, time, sys
from itertools import combinations
from api import call

RANK_CHIPS = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":10,"Q":10,"K":10,"A":11}
RANK_ORDER = {"2":2,"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"T":10,"J":11,"Q":12,"K":13,"A":14}

def chip_of(c):
    key = c.get("key","")
    # enhancements handled roughly
    return RANK_CHIPS.get(c["value"]["rank"], 0)

def classify(cards, ht):
    ranks=[c["value"]["rank"] for c in cards]; suits=[c["value"]["suit"] for c in cards]
    cnt={}
    for r in ranks: cnt[r]=cnt.get(r,0)+1
    counts=sorted(cnt.values(), reverse=True)
    n=len(cards)
    is_flush = n==5 and len(set(suits))==1
    orders=sorted(RANK_ORDER[r] for r in ranks)
    is_straight = n==5 and len(set(orders))==5 and (orders[-1]-orders[0]==4 or orders==[2,3,4,5,14])
    if n==5 and counts[0]==5 and is_flush: name="Flush Five"
    elif n==5 and counts[0]==3 and len(counts)>1 and counts[1]==2 and is_flush: name="Flush House"
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
        scoring=list(range(n))
    elif name=="High Card":
        scoring=[max(range(n), key=lambda i: RANK_ORDER[ranks[i]])]
    elif name=="Pair":
        r=max(cnt,key=lambda k:(cnt[k],RANK_ORDER[k])); scoring=[i for i in range(n) if ranks[i]==r]
    elif name=="Two Pair":
        prs=sorted([k for k in cnt if cnt[k]==2],key=lambda k:RANK_ORDER[k],reverse=True)
        scoring=[i for i in range(n) if ranks[i] in prs]
    else:
        t=max(cnt,key=lambda k:(cnt[k],RANK_ORDER[k])); scoring=[i for i in range(n) if ranks[i]==t]
    h=ht.get(name,{"chips":5,"mult":1})
    return name, h["chips"]+sum(chip_of(cards[i]) for i in scoring), h["mult"], scoring

# --- joker model -----------------------------------------------------------
def joker_effect(j, handname, ht, nplayed, cards):
    """returns (add_chips, add_mult, xmult) for a Joker dict"""
    k=j.get("key","")
    ac=m=0.0; x=1.0
    L=ht.get(handname,{})
    if k=="j_joker": m+=4
    elif k=="j_greedy_joker": m+=4   # diamond
    elif k=="j_lusty_joker": m+=4
    elif k=="j_wrathful_joker": m+=4
    elif k=="j_gluttonous_joker": m+=4
    elif k=="j_crafty_joker": m+=4
    elif k=="j_half_joker": m+=5
    elif k=="j_sly": m+=50 if handname=="Pair" else 0
    elif k=="j_wily": m+=100 if handname=="Three of a Kind" else 0
    elif k=="j_clever": m+=80 if handname in ("Two Pair","Four of a Kind") else 0
    elif k=="j_devious": m+=100 if handname=="Straight" else 0
    elif k=="j_crafty": m+=80 if handname=="Flush" else 0
    elif k=="j_banner": ac+=30
    elif k=="j_abstract": m+=3*(j.get("count",0) or 0)
    elif k=="j_duo": x*=2 if handname in ("Pair","Two Pair","Three of a Kind","Four of a Kind") else 1
    elif k=="j_trio": x*=3 if handname in ("Pair","Two Pair","Three of a Kind","Four of a Kind") else 1
    elif k=="j_family": x*=4 if handname in ("Pair","Two Pair","Three of a Kind","Four of a Kind") else 1
    elif k=="j_order": x*=3 if handname in ("Straight","Straight Flush") else 1
    elif k=="j_tribe": x*=2 if handname=="Flush" else 1
    elif k=="j_scary_face": ac+=30
    elif k=="j_odd_todd": ac+=31
    elif k=="j_scholar": ac+=20
    elif k=="j_smiley": m+=5
    elif k=="j_blue_joker": ac+=2
    elif k=="j_ice_cream": ac+=100
    elif k=="j_green_joker": m+=1
    elif k=="j_misprint":  ac+=0
    elif k=="j_bull":  ac+=2*(j.get("sell",0) or 0)
    return ac,m,x

def best_action(state):
    hand=state["hand"]["cards"]; ht=state["hands"]; jokers=state["jokers"].get("cards",[])
    n=len(hand); mx=state["hand"].get("highlighted_limit",5)
    if n==0: return None
    best=None
    for size in range(min(mx,n),0,-1):
        for idx in combinations(range(n),size):
            cards=[hand[i] for i in idx]
            name, ch, ml, sc = classify(cards, ht)
            ac=m=x=0; xm=1.0
            for j in jokers:
                a,b,c2=joker_effect(j,name,ht,n,cards)
                ac+=a; m+=b; xm*=c2
            score=(ch+ac)*(ml+m)*xm
            if best is None or score>best[0]:
                best=(score,list(idx),name,ch,ml)
    return best

def s_(**kw):
    r=call("gamestate")
    return r.get("result") or r

def wait_for(states, timeout=30):
    t0=time.time()
    while time.time()-t0<timeout:
        st=s_()
        if st["state"] in states: return st
        time.sleep(0.08)
    return s_()

def need_score(st):
    for b in ("small","big","boss"):
        if st["blinds"][b]["status"]=="CURRENT": return st["blinds"][b]["score"]
    for b in ("small","big","boss"):
        if st["blinds"][b]["status"]=="SELECT": return st["blinds"][b]["score"]
    return 0

def main(max_turns=400):
    turns=0
    while turns<max_turns:
        turns+=1
        st=s_()
        state=st["state"]; r=st.get("round",{})
        print(f"[{turns}] {state} ante{st['ante_num']} ${st['money']} chips={r.get('chips')} "
              f"hands={r.get('hands_left')} disc={r.get('discards_left')} jok={st['jokers']['count']}", flush=True)
        if state=="GAME_OVER":
            print("GAME OVER", flush=True); return "over"
        if st.get("won"):
            print("WON!", flush=True); return "won"
        if state=="BLIND_SELECT":
            res=call("select"); time.sleep(0.3)
        elif state=="SELECTING_HAND":
            best=best_action(st)
            if not best: time.sleep(0.3); continue
            score,idx,name,ch,ml=best
            target=need_score(st)
            remaining=r.get("hands_left",1)
            print(f"    best={name} {ch}x{ml}={score:.0f} cards={idx} target={target} disc={r.get('discards_left')}", flush=True)
            if score*remaining < target and r.get("discards_left",0)>0 and remaining>0:
                # discard lowest value cards: keep best hand, dump rest
                keep=set(idx); dump=[i for i in range(len(st["hand"]["cards"])) if i not in keep]
                dump=dump[:5] or idx[:1]
                res=call("discard", cards=dump); time.sleep(0.4)
            else:
                res=call("play", cards=idx)
        elif state=="ROUND_EVAL":
            call("cash_out"); time.sleep(0.4)
        elif state=="SHOP":
            handle_shop(st)
            call("next_round"); time.sleep(0.4)
        elif state in ("BUFFOON_PACK","TAROT_PACK","PLANET_PACK","SPECTRAL_PACK","STANDARD_PACK"):
            call("pack", skip=True); time.sleep(0.3)
        elif state=="NEW_ROUND":
            time.sleep(0.2)
        elif state=="MENU":
            call("start", deck="RED", stake="WHITE"); time.sleep(1.5)
        else:
            time.sleep(0.25)
    return "timeout"

def handle_shop(st):
    shop=st.get("shop",{}).get("cards",[])
    money=st["money"]
    print(f"    shop: {[(c['key'], c['cost']['buy']) for c in shop]} money=${money}", flush=True)
    for i,c in enumerate(shop):
        if c["cost"]["buy"] <= money-1 and st["jokers"]["count"]<st["jokers"]["limit"]:
            if c["cost"]["buy"]<=8:
                call("buy", card=i); time.sleep(0.3)
                money-=c["cost"]["buy"]
                break

if __name__=="__main__":
    print(main(int(sys.argv[1]) if len(sys.argv)>1 else 400))
