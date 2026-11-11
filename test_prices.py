"""Feasibility test: can we download a PriceFull file of Shufersal, Rami Levy, Yohananof and Hazi Hinam from a GitHub server (outside Israel)?
Downloads up to 2 files per chain to disk, then prints what arrived and a few sample products. Nothing is kept."""
import glob, gzip, io, os, re, traceback, zipfile
from il_supermarket_scarper import ScarpingTask

def text_of(path):
    raw = open(path, "rb").read()
    for opener in (lambda c: gzip.decompress(c),
                   lambda c: zipfile.ZipFile(io.BytesIO(c)).read(zipfile.ZipFile(io.BytesIO(c)).namelist()[0]),
                   lambda c: c):
        try:
            return opener(raw).decode("utf-8", "ignore")
        except Exception:
            pass
    return ""

def run(chain):
    print(f"\n===== {chain} =====", flush=True)
    out = os.path.join("dumps", chain)
    task = ScarpingTask(
        enabled_scrapers=[chain], files_types=["PRICE_FULL_FILE"], multiprocessing=1,
        output_configuration={"output_mode": "disk", "base_storage_path": out},
        status_configuration={"database_type": "json", "base_path": os.path.join("status", chain)})
    task.start(limit=2)
    task.join()
    files = [f for f in glob.glob(os.path.join(out, "**", "*"), recursive=True) if os.path.isfile(f)]
    for f in files:
        xml = text_of(f)
        items = re.findall(r"<Item>.*?</Item>", xml, re.S)
        print(f"file: {os.path.basename(f)}  size: {os.path.getsize(f)} bytes  items: {len(items)}")
        shown = 0
        for it in items:
            nm = re.search(r"<ItemNm>(.*?)</ItemNm>|<ItemName>(.*?)</ItemName>", it, re.S)
            pr = re.search(r"<ItemPrice>(.*?)</ItemPrice>", it)
            bc = re.search(r"<ItemCode>(.*?)</ItemCode>", it)
            n = (nm.group(1) or nm.group(2)) if nm else ""
            if "חלב" in n and "תנובה" in n and shown < 3:
                shown += 1
                print("  sample:", bc.group(1) if bc else "?", n.strip(), pr.group(1) if pr else "?")
    print(f"{chain}: {len(files)} file(s) downloaded")
    return len(files)

summary = {}
for chain in ("SHUFERSAL", "RAMI_LEVY", "YOHANANOF", "HAZI_HINAM"):
    try:
        summary[chain] = run(chain)
    except Exception:
        print(f"{chain}: FAILED"); traceback.print_exc(); summary[chain] = -1
print("\n===== SUMMARY =====")
for c, n in summary.items():
    print(f"{c}: " + ("FAILED (error)" if n < 0 else (f"OK, {n} file(s)" if n else "NO FILES (blocked or empty)")))
