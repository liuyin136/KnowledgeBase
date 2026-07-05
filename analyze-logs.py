#!/usr/bin/env python3
"""Quick analyzer for docker backend logs (NDJSON + plain lines)."""
import json
from collections import Counter

with open("backend-logs-clean.txt", encoding="utf-8", errors="ignore") as f:
    lines = [ln.rstrip() for ln in f if ln.strip()]

json_lines = []
plain_lines = []
for ln in lines:
    s = ln.strip()
    if s.startswith("{") and '"ts"' in s:
        try:
            json_lines.append(json.loads(s))
        except Exception:
            plain_lines.append(ln)
    else:
        plain_lines.append(ln)

print("=== LOG SUMMARY ===")
print(f"Total lines in clean file: {len(lines)}")
print(f"Structured JSON records:   {len(json_lines)}")
print(f"Plain/uvicorn/other lines: {len(plain_lines)}")

levels = Counter(j.get("level", "?") for j in json_lines)
print(f"\nBy level: {dict(levels)}")

events = Counter(j.get("event") for j in json_lines if j.get("event"))
print("\nEvents (count + name):")
for name, cnt in events.most_common(30):
    print(f"  {cnt:4d}  {name}")

loggers = Counter(j.get("logger", "?") for j in json_lines)
print(f"\nLoggers: {dict(loggers)}")

exp_ids = [j.get("experiment_id") for j in json_lines if j.get("experiment_id")]
print(f"\nexperiment_id values seen: {len(exp_ids)} (unique: {len(set(exp_ids))})")

print("\n=== SAMPLE: Startup sequence (first JSONs) ===")
for j in json_lines[:6]:
    slim = {k: j.get(k) for k in ("ts", "level", "logger", "message", "event", "error") if k in j}
    print(json.dumps(slim, default=str))

print("\n=== SAMPLE: A neo4j notification (typical) ===")
for j in json_lines:
    if "neo4j.notifications" in str(j.get("logger", "")):
        print(json.dumps({k: j.get(k) for k in ("level", "logger", "message", "event") if k in j}, default=str)[:500])
        break

print("\n=== LAST structured record ===")
if json_lines:
    j = json_lines[-1]
    print(json.dumps({k: j.get(k) for k in ("ts", "level", "logger", "message", "event") if k in j}, default=str))
