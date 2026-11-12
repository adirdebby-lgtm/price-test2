"""One-off helper: prints the branches (id, name, city, address) of the chains, filtered to the cities we care about."""
import asyncio, glob, os, re, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_index import text_of

CHAINS = ["FRESH_MARKET_AND_SUPER_DOSH", "RAMI_LEVY", "YOHANANOF", "OSHER_AD", "SHUFERSAL"]
WORDS = ["חולון", "בת ים", "בת-ים", "ראשון", "רמת אליהו", "ראשל"]

def stores_of(xml):
    out = []
    for st in re.findall(r"<(?:STORE|Store|Branch|SubChain)\b.*?</(?:STORE|Store|Branch|SubChain)>", xml, re.S):
        vals = {}
        for tag in ("StoreId", "StoreID", "STOREID", "StoreName", "STORENAME", "City", "CITY", "Address", "ADDRESS", "SubChainName"):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", st, re.S)
            if m:
                vals[tag.lower()] = re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip()
        if vals:
            out.append(vals)
    return out

def one(chain):
    from il_supermarket_scarper.scrapper_runner import MainScrapperRunner, _scrape_one
    out = os.path.join("dumps_stores", chain)
    runner = MainScrapperRunner(enabled_scrapers=[chain], multiprocessing=1,
        output_configuration={"output_mode": "disk", "base_storage_path": out},
        status_configuration={"database_type": "json", "base_path": os.path.join("status_stores", chain)})
    asyncio.run(_scrape_one(chain, limit=3, single_pass=True, files_types=["STORE_FILE"],
                            file_output=runner._file_outputs[chain], status_database=runner._status_databases[chain]))
    files = [f for f in glob.glob(os.path.join(out, "**", "*"), recursive=True) if os.path.isfile(f)]
    files.sort(reverse=True)
    print(f"== {chain}: {[os.path.basename(f) for f in files]}", flush=True)
    for f in files[:1]:
        xml = text_of(f)
        rows = stores_of(xml)
        print(f"   {len(rows)} stores in file")
        for r in rows:
            line = " | ".join(f"{k}={v}" for k, v in r.items())
            if any(w in line for w in WORDS):
                print("   ", line)

for c in CHAINS:
    try:
        one(c)
    except Exception:
        traceback.print_exc()
