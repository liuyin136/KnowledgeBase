import json
from collections import Counter
with open("during-logs.txt", encoding="utf-8", errors="ignore") as f:
    lines = [x.strip() for x in f if x.strip()]
jsons = []
for l in lines:
    if l.startswith("{") and '"ts"' in l[:80]:
        try:
            jsons.append(json.loads(l))
        except:
            pass
print("Structured JSON records in slice:", len(jsons))
print("Levels:", dict(Counter(j.get("level") for j in jsons)))
events = Counter(j.get("event") for j in jsons if j.get("event"))
print("Events:", dict(events))
print("\nLast 4 structured (most recent traffic):")
for j in jsons[-4:]:
    slim = {k: j.get(k) for k in ("level", "logger", "message", "event") if k in j}
    print(slim)
print("\nERROR count:", len([j for j in jsons if j.get("level") == "ERROR"]))
