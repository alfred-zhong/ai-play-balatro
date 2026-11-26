import json, sys, urllib.request

URL = "http://127.0.0.1:12346"

def call(method, **params):
    payload = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params:
        payload["params"] = params
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def state():
    return call("gamestate")["result"]

if __name__ == "__main__":
    s = state()
    print(json.dumps(s, indent=1, ensure_ascii=False)[:6000])
