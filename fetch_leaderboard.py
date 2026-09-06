"""
Fetch the public SLM Judge leaderboard into leaderboard.json.

Why this file exists: the FIRST link of the chain has to be reproducible too.
Data pasted by hand supports "I computed this". Data fetched by code supports
"run it and you get the same numbers". Only the second is checkable.

The page is an interactive Next.js app: seven of the eight tables sit behind
tabs and never appear in the served HTML. The data does arrive, embedded in the
streaming payload (self.__next_f). No browser automation needed.

Usage:
    python fetch_leaderboard.py           # fetch, validate, write
    python fetch_leaderboard.py --check   # fetch and diff against the saved file
"""

import io
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "leaderboard.json")
URL = "https://www.hume.ai/slm-judge-leaderboard"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

EXPECTED_DIMENSIONS = 8
EXPECTED_JUDGES = 7

RECORD = re.compile(
    r'\{"rank":(\d+),"model":"([^"]+)","license":"([^"]+)",'
    r'"sizeB":([^,]+),"metrics":\{"score":([-\d.]+)\}\}')


def download(url=URL):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def decode_payload(html):
    """Join the self.__next_f.push([1,"..."]) chunks back into plain text."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,(".*?")\]\)', html, re.S)
    buf = []
    for p in chunks:
        try:
            buf.append(json.loads(p))
        except Exception:
            pass
    return "".join(buf)


def extract(payload):
    """Pair each block of records with the heading that precedes it."""
    starts = [m.start() for m in re.finditer(r'\{"rank":1,', payload)]
    starts.append(len(payload))
    out = {}
    for i in range(len(starts) - 1):
        block = payload[starts[i]:starts[i + 1]]
        before = payload[max(0, starts[i] - 700):starts[i]]
        title = re.findall(r'"title":"SLM Judge - ([^"]+)"', before)
        if not title:
            continue
        out[title[-1]] = [
            dict(rank=int(r), model=m, license=l, score=float(s))
            for r, m, l, _, s in RECORD.findall(block)
        ]
    return out


def validate(data):
    """Refuse a silently corrupted fetch. Returns a list of problems."""
    problems = []
    if len(data) != EXPECTED_DIMENSIONS:
        problems.append(f"{len(data)} dimensions, expected {EXPECTED_DIMENSIONS}")
    for name, rows in data.items():
        if len(rows) != EXPECTED_JUDGES:
            problems.append(f"'{name}': {len(rows)} judges, expected {EXPECTED_JUDGES}")
        for x in rows:
            if not (-1.0 <= x["score"] <= 1.0):
                problems.append(f"'{name}' / {x['model']}: score out of range {x['score']}")
        if [x["rank"] for x in rows] != sorted(x["rank"] for x in rows):
            problems.append(f"'{name}': ranks out of order")
    # the same judge set must appear in every dimension
    if len({frozenset(x["model"] for x in r) for r in data.values()}) > 1:
        problems.append("judge set differs between dimensions")
    return problems


def fetch():
    print(f"fetching: {URL}")
    html = download()
    print(f"  {len(html):,} characters")
    payload = decode_payload(html)
    print(f"  decoded streaming payload: {len(payload):,} characters")
    data = extract(payload)
    total = sum(len(v) for v in data.values())
    print(f"  {len(data)} dimensions, {total} records")
    problems = validate(data)
    if problems:
        print("\nVALIDATION FAILED:")
        for p in problems:
            print("  -", p)
        raise SystemExit(2)
    print("  validation: OK")
    return data


def write(data):
    json.dump(data, io.open(TARGET, "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    print(f"wrote {TARGET}")


def check(data):
    """Diff the live numbers against the saved file. Non-zero exit if changed."""
    if not os.path.exists(TARGET):
        print("no saved file - run without --check first")
        return 1
    saved = json.load(io.open(TARGET, encoding="utf-8"))
    diffs = 0
    for name in sorted(set(saved) | set(data)):
        a = {x["model"]: x["score"] for x in saved.get(name, [])}
        b = {x["model"]: x["score"] for x in data.get(name, [])}
        for m in sorted(set(a) | set(b)):
            if a.get(m) != b.get(m):
                print(f"  CHANGED  {name} / {m}: {a.get(m)} -> {b.get(m)}")
                diffs += 1
    print("no differences - the saved numbers match the live page" if not diffs
          else f"{diffs} value(s) changed")
    return 0 if not diffs else 3


if __name__ == "__main__":
    d = fetch()
    sys.exit(check(d)) if "--check" in sys.argv else write(d)
