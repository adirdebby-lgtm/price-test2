"""Candidate products for the price comparison.
Downloads the full price file of ONE branch per chain (Shufersal Deal Holon-Golda 123, Rami Levy Holon 050, Yohananof Holon HaMerkava 073),
keeps only the barcodes that all three chains sell, and for each everyday item prints the cheapest candidates. Nothing is kept."""
import asyncio, glob, gzip, io, os, re, traceback, zipfile
from il_supermarket_scarper.scrapper_runner import MainScrapperRunner, _scrape_one

STORES = {"SHUFERSAL": 123, "RAMI_LEVY": 50, "YOHANANOF": 73}
SHORT = {"SHUFERSAL": "שופ", "RAMI_LEVY": "רמי", "YOHANANOF": "יוח"}

# (search word, words to exclude)
WANTED = [
    ("חלב", "שוקולד|אבקת|קוקוס|שקדים|סויה|עיזים|תינוק|מרכך|קרם|סבון|ג'ל|גוף|שיבולת|אורז|קפה|קפסול|חלבון|חלבה|מעדן|דנונה|מילקי|פודינג"),
    ("ביצים", "שוקולד|שוקו|ביצת"), ("לחם", "ממרח|פירורי|שוקולד|חמאה"), ("חמאה", "בוטנים|שקדים|שוקולד|קקאו|קרם"),
    ("קוטג", ""), ("שמנת", "קוקוס|צמחית"), ("יוגורט", "מעדן|ילדים"), ("גבינה צהובה", ""), ("גבינת שמנת", ""), ("גבינה לבנה", ""),
    ("אורז", "עוגיות|פריכיות|חלב|נס"), ("פסטה", "רוטב"), ("ספגטי", "רוטב"), ("קמח", ""), ("סוכר", "ללא|דל|תחליף|חום"), ("מלח", ""),
    ("שמן קנולה", ""), ("שמן זית", ""), ("שמן חמניות", ""), ("טונה", ""), ("קפה נמס", ""), ("תה", "קרם|סבון|שמפו|מרכך|בושם|תה קר"),
    ("שוקולד", ""), ("חומוס", "יבש"), ("טחינה", ""), ("מיונז", ""), ("קטשופ", ""), ("תירס", ""), ("מלפפונים חמוצים", ""),
    ("נייר טואלט", ""), ("מגבות נייר", ""), ("שקיות אשפה", ""), ("אבקת כביסה", ""), ("נוזל כלים", ""), ("מרכך כביסה", ""),
    ("שמפו", ""), ("משחת שיניים", ""), ("סבון", "כלים|כביסה"), ("מים מינרליים", ""), ("קולה", ""), ("מיץ", ""), ("בירה", ""),
    ("קורנפלקס", ""), ("דגני בוקר", ""), ("פיתות", ""), ("במבה", ""), ("ביסלי", ""), ("דבש", ""), ("ריבה", ""), ("עדשים", ""),
    ("עוף", "מרק|אבקת|תבלין|רוטב"), ("חזה עוף", ""), ("שניצל", ""), ("נקניקיות", ""), ("סלמון", ""), ("חציל", ""),
]

def text_of(path):
    raw = open(path, "rb").read()
    for opener in (lambda c: gzip.decompress(c),
                   lambda c: zipfile.ZipFile(io.BytesIO(c)).read(zipfile.ZipFile(io.BytesIO(c)).namelist()[0]),
                   lambda c: c):
        try:
            txt = opener(raw)
            for enc in ("utf-8", "utf-16", "cp1255"):
                try:
                    return txt.decode(enc)
                except Exception:
                    pass
        except Exception:
            pass
    return ""

def items_of(xml):
    out = {}
    for it in re.findall(r"<Item>.*?</Item>", xml, re.S | re.I):
        g = lambda *ns: next((re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip() for n in ns
                              for m in [re.search(rf"<{n}>(.*?)</{n}>", it, re.S | re.I)] if m and m.group(1).strip()), "")
        code, name, price = g("ItemCode"), g("ItemNm", "ItemName"), g("ItemPrice")
        if code and name and price:
            try:
                out[code] = (name, float(price))
            except ValueError:
                pass
    return out

def fetch(chain, store):
    out = os.path.join("dumps", chain)
    runner = MainScrapperRunner(enabled_scrapers=[chain], multiprocessing=1,
        output_configuration={"output_mode": "disk", "base_storage_path": out},
        status_configuration={"database_type": "json", "base_path": os.path.join("status", chain)})
    asyncio.run(_scrape_one(chain, limit=5, single_pass=True, files_types=["PRICE_FULL_FILE"], store_id=store,
                            file_output=runner._file_outputs[chain], status_database=runner._status_databases[chain]))
    files = [f for f in glob.glob(os.path.join(out, "**", "*"), recursive=True)
             if os.path.isfile(f) and re.search(rf"PriceFull.*-0*{store}-20\d{{6}}", os.path.basename(f))]   # exactly this branch
    files.sort()
    files = files[::-1]                                                                                    # newest first
    print(f"{chain} store {store}: files = {[os.path.basename(f) for f in files]}", flush=True)
    return items_of(text_of(files[0])) if files else {}

data = {}
for chain, store in STORES.items():
    try:
        data[chain] = fetch(chain, store)
        print(f"{chain}: {len(data[chain])} items", flush=True)
    except Exception:
        print(f"{chain}: FAILED"); traceback.print_exc(); data[chain] = {}

common = set.intersection(*[set(d) for d in data.values() if d]) if all(data.values()) else set()
print(f"\nbarcodes sold by all three chains: {len(common)}")
print("\n===== CANDIDATES (cheapest first) =====")
for word, bad in WANTED:
    rows = []
    for code in common:
        n0 = data["SHUFERSAL"][code][0]
        if word in n0 and not (bad and re.search(bad, n0)):
            rows.append((min(data[c][code][1] for c in data), code))
    rows.sort()
    print(f"\n## {word}  ({len(rows)} candidates)")
    for _, code in rows[:6]:
        cells = " | ".join(f"{SHORT[c]} {data[c][code][1]:.2f}" for c in STORES)
        print(f"  {code}  {data['SHUFERSAL'][code][0]}  ::  {cells}")
print("\n===== SUMMARY =====")
for c in STORES:
    print(f"{c}: {len(data[c])} items" if data[c] else f"{c}: NO DATA")
