import json, urllib.request, urllib.parse, time, datetime
UA = {"User-Agent": "Mozilla/5.0"}
syms = ["^GDAXI","^GSPC","^IXIC","^NDX","^STOXX50E","BZ=F","CL=F","GC=F","EURUSD=X","BTC-EUR","ETH-EUR","^VIX","SAP.DE"]
for s in syms:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(s) + "?range=1mo&interval=1d"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
            j = json.load(r)
        res = j["chart"]["result"][0]; m = res["meta"]
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
        prev = m.get("chartPreviousClose")
        print(f"{s:10} {r.status} {m.get('shortName','').strip()[:22]:22} {m.get('currency')} price={m.get('regularMarketPrice')} prevClose(range)={prev} n={len(closes)} last5={[round(c,2) for c in closes[-5:]]} t={datetime.datetime.fromtimestamp(m['regularMarketTime'], datetime.timezone.utc):%Y-%m-%d %H:%M}Z")
    except Exception as e:
        print(s, "FEHLER", e)
    time.sleep(0.3)
# urllib default UA
try:
    urllib.request.urlopen("https://query1.finance.yahoo.com/v8/finance/chart/%5EGDAXI?range=5d&interval=1d", timeout=15)
    print("default UA ok")
except Exception as e:
    print("default UA:", e)
