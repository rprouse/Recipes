"""
Fetch NYT Cooking recipe pages and cache the parsed data. No login required:
the full schema.org/Recipe JSON-LD (name, author, times, yield, ingredients,
steps, image) AND the cook's tip are in the raw server HTML.

Resumable: skips recipes already imported into the vault (any .md whose body
contains the recipe id) and recipes already cached.

Usage:
    python nyt_fetch.py <manifest.json> [--vault PATH] [--work DIR]

manifest.json: [{"id": "...", "url": "https://cooking.nytimes.com/recipes/..."}]
Vault defaults to $RECIPE_VAULT or the current working directory.
Outputs (under <work>, default <vault>/.recipe-import):
    cache/<id>.json       parsed fields per recipe
    classify_input.json   [{id,title,category,keywords}] for the folder step
"""
import os, re, json, time, argparse, urllib.request, urllib.error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
DEC = json.JSONDecoder()


def fetch(url, tries=3):
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError):
            if n == tries - 1:
                raise
            time.sleep(2 * (n + 1))


def find_recipe_jsonld(html):
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        cands = [data]
        if isinstance(data, list):
            cands = data
        elif isinstance(data, dict) and "@graph" in data:
            cands = data["@graph"]
        for c in cands:
            if isinstance(c, dict):
                t = c.get("@type")
                if t == "Recipe" or (isinstance(t, list) and "Recipe" in t):
                    return c
    return None


def flatten_steps(instructions):
    steps = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
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
            url, w = i.get("url") or i.get("contentUrl"), int(i.get("width") or 0)
        else:
            url, w = i, 0
        if not url:
            continue
        if "videoSixteenByNineJumbo1600" in url:
            return url
        if w > best_w:
            best, best_w = url, w
    return best


def fallback_image(html):
    """Some recipes ship a null JSON-LD `image`; recover the lead photo from the
    og:image meta tag, upgrading to the largest 16:9 crop of the SAME asset when
    that crop is present in the HTML (confirmed by scraping, not by guessing)."""
    m = (re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html)
         or re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html))
    if not m:
        return None
    og = m.group(1)
    asset = og.rsplit("/", 1)[0]  # directory holding every crop of this photo
    big = re.findall(re.escape(asset) + r'/[^"\']*videoSixteenByNineJumbo1600[^"\']*\.jpg', html)
    return big[0] if big else og


def extract_tip(html):
    """Tip is in embedded app data as "tips":[{ScoopRecipeTip...}], NOT in JSON-LD."""
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
    h, mn = int(m.group(1) or 0), int(m.group(2) or 0)
    parts = []
    if h:
        parts.append(f"{h} hour" + ("s" if h != 1 else ""))
    if mn:
        parts.append(f"{mn} minutes")
    return " ".join(parts) or "0 minutes"


def imported_ids(vault):
    ids = set()
    for root, _, files in os.walk(vault):
        if ".recipe-import" in root or ".git" in root or os.sep + ".claude" in root:
            continue
        for f in files:
            if f.endswith(".md"):
                try:
                    txt = open(os.path.join(root, f), encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                ids.update(re.findall(r"cooking\.nytimes\.com/recipes/(\d+)", txt))
    return ids


def parse_recipe(rid, url, html, fallback_title=""):
    rec = find_recipe_jsonld(html)
    if not rec:
        return None
    author = rec.get("author")
    return {
        "id": rid, "url": url,
        "name": (rec.get("name") or fallback_title).strip(),
        "author": author.get("name", "") if isinstance(author, dict) else (author[0].get("name", "") if isinstance(author, list) and author and isinstance(author[0], dict) else ""),
        "yield": rec.get("recipeYield", ""),
        "time": iso_to_human(rec.get("totalTime")),
        "category": rec.get("recipeCategory", ""),
        "keywords": rec.get("keywords", ""),
        "diet": rec.get("suitableForDiet", ""),
        "description": (rec.get("description") or "").strip(),
        "ingredients": [i.strip() for i in rec.get("recipeIngredient", [])],
        "steps": flatten_steps(rec.get("recipeInstructions")),
        "image": pick_image(rec.get("image")) or fallback_image(html),
        "tip": extract_tip(html),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--vault", default=os.environ.get("RECIPE_VAULT") or os.getcwd())
    ap.add_argument("--work", default=None)
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between fetches (be polite)")
    args = ap.parse_args()
    vault = os.path.abspath(args.vault)
    work = args.work or os.path.join(vault, ".recipe-import")
    cache = os.path.join(work, "cache")
    os.makedirs(cache, exist_ok=True)

    manifest = json.load(open(args.manifest, encoding="utf-8"))
    imported = imported_ids(vault)
    classify, skipped, failed = [], 0, []
    for r in manifest:
        rid = r["id"]
        cache_f = os.path.join(cache, rid + ".json")
        if rid in imported:
            skipped += 1
            continue
        if os.path.exists(cache_f):
            data = json.load(open(cache_f, encoding="utf-8"))
        else:
            try:
                data = parse_recipe(rid, r["url"], fetch(r["url"]), r.get("title", ""))
            except Exception as e:
                failed.append((rid, str(e)))
                continue
            if not data:
                failed.append((rid, "no JSON-LD Recipe"))
                continue
            json.dump(data, open(cache_f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            time.sleep(args.sleep)
        classify.append({"id": rid, "title": data["name"], "category": data.get("category", ""), "keywords": data.get("keywords", "")})

    json.dump(classify, open(os.path.join(work, "classify_input.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"cached/ready: {len(classify)}  skipped(existing): {skipped}  failed: {len(failed)}")
    for rid, why in failed:
        print("  FAILED", rid, why)


if __name__ == "__main__":
    main()
