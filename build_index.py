"""Daily price index for the fridge kiosk.
Downloads the full price file of one branch per chain (Shufersal Deal Holon-Golda 123, Rami Levy Bat Yam 045,
Yohananof Rishon Ramat Eliyahu 028, Super Dosh Holon 039, Osher Ad Rishon 025), keeps the barcodes that all the chains sell, and for each everyday product type
writes the "regular cheapest" product first, followed by other variants (so the device can narrow by words like 3% or נטול לקטוז).
Output: prices.tsv (a few dozen KB) that the kiosk downloads once a day."""
import asyncio, datetime, glob, gzip, io, os, re, sys, traceback, zipfile

STORES = {"SHUFERSAL": 123, "RAMI_LEVY": 45, "YOHANANOF": 28,
          "FRESH_MARKET_AND_SUPER_DOSH": 39, "OSHER_AD": 25}
CHAIN_NAMES = {"SHUFERSAL": "שופרסל", "RAMI_LEVY": "רמי לוי", "YOHANANOF": "יוחננוף",
               "FRESH_MARKET_AND_SUPER_DOSH": "סופר דוש", "OSHER_AD": "אושר עד"}
MAX_VARIANTS = 10
L1 = r"(?<![\d.,])1\s?ל(?![א-ת])|1\s?ליטר|ליטר"          # "1ל" / "1 ליטר"

# (keyword the family says, regex the Shufersal name must match, regex it must NOT match, regex for the usual pack size or "")
SPECS = [
    ('חלב',
     r"^חלב",
     (
         r"שוקולד|וניל|בננה|פטל|תות|אבקת|קוקוס|שקדים|"
         r"סויה|שיבולת|אורז|קפה|חלבון|מעדן|מילקי|פודינג|"
         r"משקה|מ\.חלב|חלבי|תינוק|מרכך|קרם|סבון"),
     L1),
    ('קוטג',
     r"קוטג",
     r"",
     r"250"),
    ('שמנת',
     r"שמנת",
     (
         r"בצל|קוקוס|צמחית|שום|גבינת|פוף|דובונים|תפוצ|"
         r"חטיף|בטעם|רוטב|פרווה"),
     r"200|250"),
    ('יוגורט',
     r"יוגורט",
     r"ילדים|מעדן|משקה|גרנולה|חטיף",
     r""),
    ('גבינה לבנה',
     r"גבינה לבנה",
     r"",
     r"250"),
    ('גבינה צהובה',
     r"גבינה צהובה",
     r"",
     r"200|250|400"),
    ('גבינת שמנת',
     r"גבינת שמנת",
     r"",
     r""),
    ('חמאה',
     r"חמאה",
     (
         r"בטעם|סוכריות|בוטנים|שקדים|קרם|מרגרינה|"
         r"נטורינה|בלובנד|פופקו|קקאו|שוקולד|דבש|סבון|"
         r"עוגיות"),
     r"200|250|100"),
    ('מרגרינה',
     r"מרגרינה|נטורינה|בלובנד",
     r"בטעם חמאה ודבש|ללא מלח",
     r""),
    ('לחם',
     r"^לחם",
     (
         r"קמח|ממרח|פירורי|שוקולד|חמאה|לחמניות|טורטיה|"
         r"חריץ"),
     r""),
    ('פיתות',
     r"^פיתות|^פיתה",
     r"",
     r""),
    ('אורז',
     r"^אורז",
     (
         r"עוגיות|פריכ|חלב|נס|מרק|משקה|וופל|פתיתים|דגני|"
         r"בטעם|מוכן|כוסות|מנה"),
     r"1\s?ק|500|1000"),
    ('פסטה',
     r"^פסטה",
     r"רוטב|טונה|מנה חמה|סלט|ארוחה|מוכן|נודלס",
     r"500"),
    ('ספגטי',
     r"ספגטי",
     r"רוטב|מנה חמה|בולונז|סלט|ארוחה|נודלס",
     r"500"),
    ('מקרוני',
     r"מקרוני",
     r"גבינה|מנה|סלט",
     r"500"),
    ('אטריות',
     r"^אטריות",
     r"מנה|מרק|נודלס|סינית|נמס",
     r""),
    ('פתיתים',
     r"^פתיתים",
     r"קוואקר|תינוקות|גרנולה",
     r""),
    ('קוסקוס',
     r"^קוסקוס",
     r"",
     r""),
    ('קמח',
     r"^קמח",
     r"טורטיה|עלי|עוגיות|ללא",
     r"1\s?ק|1000"),
    ('סוכר',
     r"^סוכר",
     (
         r"סוכריות|אבקת|ללא|דל|תחליף|קנים|חום|מילקי|"
         r"עוגיות|וניל|בטעם"),
     r"1\s?ק|500|1000"),
    ('מלח',
     r"^מלח",
     r"פריכ|מרגרינה|פלפל|חטיף|במלח",
     r""),
    ('שמן קנולה',
     r"^שמן קנולה",
     r"טונה|תרסיס|נתחי|פסטה|לבנה|סרדין",
     L1),
    ('שמן זית',
     r"שמן זית",
     (
         r"ב\s?שמן זית|טונה|תרסיס|לבנה|פסטה|סרדין|זיתים|"
         r"סבון|קרם|שמפו|תבלין"),
     r""),
    ('שמן חמניות',
     r"^שמן חמניות",
     r"",
     L1),
    ('טונה',
     r"טונה",
     (
         r"סלט|פסטה|אורז|חתול|פריסקיז|פנסי|ירקות|"
         r"נ\.פילה|מרק|ס\.ק|חומוס|גרגיר|תירס|שעועית|"
         r"עגבני"),
     r""),
    ('קפה',
     (
         r"קפה נמס|נס קפה|קפה טחון|קפה שחור|קפה טורקי|"
         r"קפה עלית"),
     (
         r"פינוקיות|קרם|וניל|שוקו|קר|קפסול|חלב|בטעם|"
         r"ביסקוויט|עוגיות|גלידה|ממרח|3\s?ב"),
     r"200|100|50"),
    ('תה',
     r"^תה",
     (
         r"קר|ספרינג|פרח|אייס|משקה|קרם|סבון|מרכך|שמפו|"
         r"בושם|תבלין"),
     r""),
    ('שוקולד',
     r"^שוקולד",
     (
         r"ממרח|מעדן|קרם|אבקת|משקה|פתיתי|כדורי|עוגה|"
         r"גלידה|חטיף|ביסקוויט|וופל|קורנפלקס|דגנים"),
     r""),
    ('חומוס',
     r"^חומוס",
     r"יבש|עם|חצילים|חטיף|בטעם|סלט|גרגרי",
     r""),
    ('גרגרי חומוס',
     r"גרגרי חומוס|שימורי חומוס",
     r"",
     r""),
    ('טחינה',
     r"^טחינה",
     r"חומוס|חציל|ממרח|חלווה|חלבה|עוגיות|סלט",
     r""),
    ('מיונז',
     r"^מיונז",
     r"",
     r""),
    ('קטשופ',
     r"^קטשופ",
     r"",
     r""),
    ('חרדל',
     r"^חרדל",
     r"",
     r""),
    ('חומץ',
     r"^חומץ",
     r"",
     r""),
    ('תירס',
     r"^(שימורי )?תירס",
     r"שניצל|חטיף|פופקורן|פריכ|קפוא|גרעיני",
     r""),
    ('מלפפונים חמוצים',
     r"מלפפו",
     r"טרי",
     r"חמוצ|במלח|בחומץ|מלפפו\.ב"),
    ('רסק עגבניות',
     r"רסק עגבני|ר\.? ?עגבני|רסק מרוכז",
     r"עוף|טונה|פסטה|פיצה|רוטב",
     r""),
    ('נייר טואלט',
     r"נייר טואלט|ניר טואלט|נ\.טואלט",
     r"",
     r""),
    ('מגבות נייר',
     r"מגבות נייר|מגבת נייר|ניר מטבח",
     r"",
     r""),
    ('שקיות אשפה',
     r"שקיות אשפה|שקיות זבל|שקית אשפה|שקיות לאשפה",
     r"",
     r""),
    ('כביסה',
     (
         r"אבקת כביסה|אבקה לכביסה|ג'ל כביסה|נוזל כביסה|"
         r"קפסולות כביסה"),
     r"מרכך|מסיר|כתמים|מנקה|מכונת",
     r""),
    ('מרכך כביסה',
     r"מרכך",
     r"שיער|שמפו|קונדישנר",
     r""),
    ('נוזל כלים',
     r"פיירי|סנו|נוזל ל?כלים|סבון ל?כלים|ג'ל ל?כלים",
     r"מדיח",
     r""),
    ('שמפו',
     r"שמפו",
     r"קרם|מרכך|כלב",
     r""),
    ('משחת שיניים',
     r"משחת שיניים",
     r"",
     r""),
    ('סבון',
     r"^סבון",
     r"כלים|כביסה|כלי",
     r""),
    ('מים',
     r"^(מי )?(עדן|נביעות|מים)|מים מינרליים",
     (
         r"חמצן|קרם|פנים|ורדים|טעם|מעדן|נוזל|טוניק|סבון|"
         r"מי פה"),
     r"1\.5|1,5|ליטר"),
    ('קולה',
     r"קולה",
     r"",
     r""),
    ('מיץ',
     r"^מיץ|פרימור|פרי גיל",
     r"משומר|לימון|ליים|רימון",
     r""),
    ('בירה',
     r"^בירה|גולדסטאר|קרלסברג|הייניקן",
     r"",
     r""),
    ('קורנפלקס',
     r"קורנפלקס|קורן פלקס",
     r"מילקי|טופ|מעדן|חטיף|שוקולד|עוגיות|חלב",
     r""),
    ('במבה',
     r"במבה",
     r"מתוקה|נוגט|שוקולד",
     r"60|80|100"),
    ('ביסלי',
     r"ביסלי",
     r"",
     r""),
    ('פופקורן',
     r"פופקורן",
     r"",
     r""),
    ('דבש',
     r"דבש",
     (
         r"חרדל|ממרח|עוגיות|טעם|פופקו|עוגת|שיפון|וופל|"
         r"חטיף|קרם|סבון|שוקולד|גרנולה|ביסקוויט|חמאה|תה|"
         r"קפה|תירס|שקדים|בוטנים|מיץ|בייגל|ויסקי|דבשת"),
     r""),
    ('ריבה',
     r"^ריבה|^ריבת|^ממרח ריבה",
     r"",
     r""),
    ('עדשים',
     r"עדשים",
     (
         r"אורז|מרק|מנה|שניצל|סלט|נודלס|ירקות|קציצות|"
         r"בולגור|מילקי|טופ|שוקולד|סוכריות|דראז|חטיף|"
         r"ממרח|עוגי"),
     r""),
    ('נקניקיות',
     r"^נקניקיות",
     r"",
     r""),
    ('שניצל',
     r"^שניצל",
     r"",
     r""),
    ("צ'יפס",
     r"^צ.יפס|^צ'יפס",
     r"",
     r""),
    ('עוגיות',
     r"^עוגיות",
     r"בצק",
     r""),
]

# words that make a product "special": the family gets the plain version unless it asks for these
SPECIAL = re.compile(r"(?<![א-ת])(נטול|דל|ללא|לייט|אורגני|בטעם|עיזים|טבעוני|זירו|דיאט|פרו|מופחת|קפסולות|בייבי|מועשר ב)(?![א-ת])")

def build(data):
    """data: {chain: {barcode: (name, price)}} -> (tsv text, report text)"""
    chains = list(CHAIN_NAMES)
    common = set.intersection(*[set(data[c]) for c in chains])
    lines, report, kw_done = [], [], 0
    for kw, inc, exc, size in SPECS:
        cands = []
        for code in common:
            name = data["SHUFERSAL"][code][0]
            if re.search(inc, name) and not (exc and re.search(exc, name)):
                prices = [data[c][code][1] for c in chains]
                if min(prices) > 0:
                    cands.append((name, prices, code))
        if not cands:
            report.append(f"{kw}: NO CANDIDATES")
            continue
        def key(x):
            name, prices, _ = x
            special = 1 if SPECIAL.search(name) else 0
            sized = 0 if (not size or re.search(size, name)) else 1          # usual pack size first
            avg = sum(prices) / len(prices)
            return (special, sized, avg)
        cands.sort(key=key)
        seen, picked = set(), []
        for name, prices, code in cands:
            if (name, tuple(prices)) in seen:
                continue
            seen.add((name, tuple(prices)))
            picked.append((name, prices))
            if len(picked) >= MAX_VARIANTS:
                break
        kw_done += 1
        for name, prices in picked:
            lines.append("\t".join([kw, name.replace("\t", " ")] + [f"{p:.2f}" for p in prices]))
        report.append(f"{kw}: {len(cands)} candidates -> default: {picked[0][0]}  " + " | ".join(f"{p:.2f}" for p in picked[0][1]))
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2))).date().isoformat()
    head = ["#v1", f"#date\t{today}", "#place\tחולון · בת ים · ראשל״צ", "#chains\t" + "\t".join(CHAIN_NAMES[c] for c in chains)]
    return "\n".join(head + lines) + "\n", report, kw_done

# ---------------------------------------------------------------------------------------------- download
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
    from il_supermarket_scarper.scrapper_runner import MainScrapperRunner, _scrape_one
    out = os.path.join("dumps", chain)
    runner = MainScrapperRunner(enabled_scrapers=[chain], multiprocessing=1,
        output_configuration={"output_mode": "disk", "base_storage_path": out},
        status_configuration={"database_type": "json", "base_path": os.path.join("status", chain)})
    asyncio.run(_scrape_one(chain, limit=5, single_pass=True, files_types=["PRICE_FULL_FILE"], store_id=store,
                            file_output=runner._file_outputs[chain], status_database=runner._status_databases[chain]))
    files = [f for f in glob.glob(os.path.join(out, "**", "*"), recursive=True)
             if os.path.isfile(f) and re.search(rf"PriceFull.*-0*{store}-20\d{{6}}", os.path.basename(f))]
    files.sort(reverse=True)                                                                                 # newest first
    print(f"{chain} store {store}: {[os.path.basename(f) for f in files]}", flush=True)
    return items_of(text_of(files[0])) if files else {}

def main():
    data = {}
    for chain, store in STORES.items():
        for attempt in (1, 2, 3):
            try:
                data[chain] = fetch(chain, store)
            except Exception:
                traceback.print_exc(); data[chain] = {}
            if data[chain]:
                break
            print(f"{chain}: attempt {attempt} failed", flush=True)
        print(f"{chain}: {len(data[chain])} items", flush=True)
    if not all(data.values()):
        print("missing data for a chain: prices.tsv NOT updated")
        sys.exit(1)
    tsv, report, kw_done = build(data)
    print("\n".join(report))
    if kw_done < 20:
        print(f"only {kw_done} product types found: prices.tsv NOT updated")
        sys.exit(1)
    open("prices.tsv", "w", encoding="utf-8").write(tsv)
    print(f"prices.tsv written: {kw_done} product types, {len(tsv)} bytes")

if __name__ == "__main__":
    main()
