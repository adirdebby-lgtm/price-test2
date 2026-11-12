"""Diagnostic: where does a product word appear in each chain (barcode, name, price)? usage: python diag.py סוכר"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_index as b
word = sys.argv[1] if len(sys.argv) > 1 else "סוכר"
data = {}
for chain, store in b.STORES.items():
    try:
        data[chain] = b.fetch(chain, store)
    except Exception as e:
        print(chain, "failed", e); data[chain] = {}
codes = {c: {k for k, (n, p) in d.items() if word in n} for c, d in data.items()}
allc = set.union(*codes.values()) if codes else set()
print(f"\n=== '{word}' ===")
for c, s in codes.items():
    print(f"{c}: {len(s)} items contain the word")
print("\nbarcode | chains having it (S=Shufersal R=Rami Y=Yohananof D=Dosh O=OsherAd) | name")
tag = {"SHUFERSAL": "S", "RAMI_LEVY": "R", "YOHANANOF": "Y", "FRESH_MARKET_AND_SUPER_DOSH": "D", "OSHER_AD": "O"}
rows = []
for code in allc:
    have = "".join(tag[c] if code in data[c] else "-" for c in data)
    name = next(data[c][code][0] for c in data if code in data[c] and word in data[c][code][0])
    rows.append((have.count("-"), code, have, name))
for _, code, have, name in sorted(rows)[:60]:
    print(code, have, name)
