"""
Fetch NYT Cooking recipe pages (no auth needed — JSON-LD is in the server HTML)
and cache the parsed data. Resumable: skips recipes already imported into the
vault and recipes already cached.

Usage: python fetch_parse.py <manifest.json>
Outputs:
  .recipe-import/cache/<id>.json      one per recipe (parsed fields)
  .recipe-import/classify_input.json  [{id,title,category,keywords}] for folder step
"""
import sys, os, re, json, time, urllib.request, urllib.error

VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(VAULT, ".recipe-import")
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
DEC = json.JSONDecoder()


def fetch(url, tries=3):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as e:
            if n == tries - 1:
                raise
            time.sleep(2 * (n + 1))


def find_recipe_jsonld(html):
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        cands = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        if isinstance(data, dict) and "@graph" not in data:
            cands = [data]
        for c in cands:
            if not isinstance(c, dict):
                continue
            t = c.get("@type")
            if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
                return c
    return None


def flatten_steps(instructions):
    steps = []

    def walk(n):
        if n is None:
            return
        if isinstance(n, list):
            for x in n:
                walk(x)
            return
        if isinstance(n, dict):
            t = n.get("@type")
            if t == "HowToStep" and n.get("text"):
                steps.append(n["text"].strip())
            elif t == "HowToSection":
                walk(n.get("itemListElement"))
    walk(instructions)
    return steps


def pick_image(img):
    items = img if isinstance(img, list) else [img]
    best, best_w = None, -1
    for i in items:
        if isinstance(i, dict):
            url = i.get("url") or i.get("contentUrl")
            w = int(i.get("width") or 0)
        else:
            url, w = i, 0
        if not url:
            continue
        if "videoSixteenByNineJumbo1600" in url:
            return url
        if w > best_w:
            best, best_w = url, w
    return best


def extract_tip(html):
    """Tip lives in embedded app data as "tips":[{ScoopRecipeTip...}], not JSON-LD."""
    i = html.find('"tips":')
    if i == -1:
        return None
    try:
        tips, _ = DEC.raw_decode(html, i + len('"tips":'))
    except json.JSONDecodeError:
        return None
    texts = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            if isinstance(n.get("text"), str):
                texts.append(n["text"])
            for v in n.values():
                if isinstance(v, (list, dict)):
                    walk(v)
    walk(tips)
    tip = " ".join(t.strip() for t in texts if t.strip())
    return tip or None


def iso_to_human(iso):
    if not iso:
        return ""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso)
    if not m:
        return ""
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    parts = []
    if h:
        parts.append(f"{h} hour" + ("s" if h != 1 else ""))
    if mn:
        parts.append(f"{mn} minutes")
    return " ".join(parts) or "0 minutes"


def main():
    manifest = json.load(open(sys.argv[1], encoding="utf-8"))

    # already-imported ids (scan vault for recipe links)
    imported = set()
    for root, _, files in os.walk(VAULT):
        if ".recipe-import" in root or ".git" in root:
            continue
        for f in files:
            if f.endswith(".md"):
                try:
                    txt = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for rid in re.findall(r"cooking\.nytimes\.com/recipes/(\d+)", txt):
                    imported.add(rid)

    classify, skipped, failed = [], [], []
    for r in manifest:
        rid = r["id"]
        cache_f = os.path.join(CACHE, rid + ".json")
        if rid in imported:
            skipped.append((rid, "already in vault"))
            continue
        if os.path.exists(cache_f):
            data = json.load(open(cache_f, encoding="utf-8"))
        else:
            try:
                html = fetch(r["url"])
            except Exception as e:
                failed.append((rid, str(e)))
                continue
            rec = find_recipe_jsonld(html)
            if not rec:
                failed.append((rid, "no JSON-LD Recipe"))
                continue
            data = {
                "id": rid,
                "url": r["url"],
                "name": rec.get("name", r["title"]).strip(),
                "author": (rec.get("author") or {}).get("name", "") if isinstance(rec.get("author"), dict) else "",
                "yield": rec.get("recipeYield", ""),
                "time": iso_to_human(rec.get("totalTime")),
                "category": rec.get("recipeCategory", ""),
                "keywords": rec.get("keywords", ""),
                "diet": rec.get("suitableForDiet", ""),
                "description": (rec.get("description") or "").strip(),
                "ingredients": [i.strip() for i in rec.get("recipeIngredient", [])],
                "steps": flatten_steps(rec.get("recipeInstructions")),
                "image": pick_image(rec.get("image")),
                "tip": extract_tip(html),
            }
            json.dump(data, open(cache_f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            time.sleep(1.0)  # be polite to NYT
        classify.append({"id": rid, "title": data["name"], "category": data.get("category", ""), "keywords": data.get("keywords", "")})

    json.dump(classify, open(os.path.join(HERE, "classify_input.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"cached/ready: {len(classify)}  skipped(existing): {len(skipped)}  failed: {len(failed)}")
    for rid, why in failed:
        print("  FAILED", rid, why)
    for rid, why in skipped:
        print("  skip", rid, why)


if __name__ == "__main__":
    main()
