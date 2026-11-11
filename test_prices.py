"""Find the store branches near Holon (Kiryat Ben Gurion) for Shufersal, Rami Levy and Yohananof.
Downloads each chain's stores file and prints the stores in Holon / Bat Yam / Rishon / Tel Aviv / Azor. Nothing is kept."""
import glob, gzip, io, os, re, traceback, zipfile
from il_supermarket_scarper import ScarpingTask

CITIES = ("חולון", "בת ים", "בת-ים", "ראשון", "תל אביב", "תל-אביב", "אזור", "יפו")

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

def field(block, *names):
    for n in names:
        m = re.search(rf"<{n}>(.*?)</{n}>", block, re.S | re.I)
        if m and m.group(1).strip():
            return re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip()
    return ""

def parse_stores(xml):
    out = []
    for m in re.finditer(r"<(store|branch)>(.*?)</\1>", xml, re.S | re.I):
        b = m.group(2)
        out.append((field(b, "StoreId", "StoreID", "BranchId"), field(b, "StoreName", "BranchName"),
                    field(b, "Address"), field(b, "City")))
    return out

def run(chain):
    print(f"\n===== {chain} =====", flush=True)
    out = os.path.join("dumps", chain)
    task = ScarpingTask(
        enabled_scrapers=[chain], files_types=["STORE_FILE"], multiprocessing=1,
        output_configuration={"output_mode": "disk", "base_storage_path": out},
        status_configuration={"database_type": "json", "base_path": os.path.join("status", chain)})
    task.start(limit=1)
    task.join()
    files = [f for f in glob.glob(os.path.join(out, "**", "*"), recursive=True) if os.path.isfile(f)]
    total = 0
    for f in files:
        stores = parse_stores(text_of(f))
        total += len(stores)
        print(f"file: {os.path.basename(f)}  stores in file: {len(stores)}")
        hits = [s for s in stores if any(c in (s[1] + " " + s[2] + " " + s[3]) for c in CITIES)]
        for sid, name, addr, city in hits:
            print(f"  STORE id={sid} | {name} | {addr} | {city}")
        if not hits:
            for s in stores[:5]:
                print("  (no match, first stores)", s)
    print(f"{chain}: {len(files)} file(s), {total} stores")
    return total

summary = {}
for chain in ("SHUFERSAL", "RAMI_LEVY", "YOHANANOF"):
    try:
        summary[chain] = run(chain)
    except Exception:
        print(f"{chain}: FAILED"); traceback.print_exc(); summary[chain] = -1
print("\n===== SUMMARY =====")
for c, n in summary.items():
    print(f"{c}: " + ("FAILED (error)" if n < 0 else f"{n} stores"))
