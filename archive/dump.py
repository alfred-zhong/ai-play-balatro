import json
from api import call
s = call("gamestate")["result"]
def strip(o, depth=0):
    if isinstance(o, dict):
        return {k: strip(v, depth+1) for k,v in o.items() if k not in ("hands",)}
    if isinstance(o, list):
        return [strip(x, depth+1) for x in o[:12]]
    return o
print(json.dumps(strip(s), ensure_ascii=False, indent=1)[:4000])
