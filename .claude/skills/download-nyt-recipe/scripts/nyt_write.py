"""
Write Obsidian recipe notes from cached recipe data + folder assignments, and
download each lead image into <Folder>/attachments/.

Resumable AND collision-safe: a recipe is skipped only if its OWN note already
exists (its id is in the file). If a different recipe already owns the target
filename, this disambiguates (appends author, then id) rather than silently
shadowing it.

Usage:
    python nyt_write.py [--vault PATH] [--work DIR]

Reads <work>/cache/<id>.json and <work>/folders.json
  folders.json: {"assignments": {"<id>": "<Folder>", ...}}
Writes <vault>/<Folder>/<Name>.md and <vault>/<Folder>/attachments/<Name>.jpg
"""
import os, re, json, time, datetime, argparse, urllib.request, urllib.error

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
TODAY = datetime.date.today().strftime("%Y-%m-%d %A")

# keyword -> tag: keep only useful descriptors, drop noisy ingredient/method keywords
DESCRIPTORS = {
    "quick", "easy", "weeknight", "make-ahead", "one-pot", "one-pan", "sheet-pan",
    "slow-cooker", "no-cook", "vegetarian", "vegan", "healthy", "budget",
    "freezer-friendly", "gluten-free", "dairy-free", "kid-friendly", "spicy",
    "grilling", "spring", "summer", "fall", "winter", "holiday", "party",
    "great-leftovers", "high-protein", "low-carb",
}


def slug_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "", name or "").strip()


def _as_text(v):
    """JSON-LD fields like keywords/suitableForDiet may be a str OR a list."""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return v or ""


def make_tags(folder, keywords, diet):
    tags = [folder.lower().replace(" ", "-")]
    for kw in _as_text(keywords).split(","):
        k = kw.strip().lower().replace(" ", "-")
        if k in DESCRIPTORS and k not in tags:
            tags.append(k)
    d = _as_text(diet).lower()
    if "vegan" in d and "vegan" not in tags:
        tags.append("vegan")
    elif "vegetarian" in d and "vegetarian" not in tags:
        tags.append("vegetarian")
    return tags


def yield_str(y):
    if isinstance(y, list):
        y = next((x for x in y if isinstance(x, str)), "")
    return (y or "").strip()


def download(url, dest, tries=3):
    if os.path.exists(dest):
        return True
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) < 1000:
                return False
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except (urllib.error.URLError, TimeoutError):
            if n == tries - 1:
                return False
            time.sleep(2)


def build_note(d, folder, img_base=None):
    name = d["name"]
    img_base = img_base or slug_filename(name)
    tags = make_tags(folder, d.get("keywords"), d.get("diet"))
    fm = ["---", f"tags: [{', '.join(tags)}]", f"title: {name}"]
    if d.get("author"):
        fm.append(f"author: {d['author']}")
    fm.append(f"servings: {yield_str(d.get('yield'))}")
    fm.append(f"time: {d.get('time', '')}")
    fm.append(f"date: {TODAY}")
    fm.append(f"link: {d['url']}")
    fm.append("---")
    body = ["\n".join(fm)]
    if d.get("image"):
        body.append(f"![[attachments/{img_base}.jpg]]")
    body.append(f"# {name}")
    if d.get("description"):
        body.append(d["description"])
    body.append("### 🛒 Ingredients\n" + "\n".join(f"- {i}" for i in d["ingredients"]))
    body.append("### 🥣 Steps\n" + "\n".join(f"{n}. {s}" for n, s in enumerate(d["steps"], 1)))
    if d.get("tip"):
        tip_lines = "\n".join(f"> {ln}" for ln in d["tip"].split("\n"))
        body.append(f"> [!tip] Tip\n{tip_lines}")
    return "\n\n".join(body) + "\n"


def resolve_filename(folder_dir, base, author, rid):
    """Pick a filename that won't shadow a different recipe of the same title."""
    candidates = [base]
    if author:
        candidates.append(f"{base} - {slug_filename(author)}")
    candidates.append(f"{base} ({rid})")
    for cand in candidates:
        p = os.path.join(folder_dir, cand + ".md")
        if not os.path.exists(p):
            return cand, False
        if rid in open(p, encoding="utf-8", errors="ignore").read():
            return cand, True  # this exact recipe already written
    return f"{base} ({rid})", False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("RECIPE_VAULT") or os.getcwd())
    ap.add_argument("--work", default=None)
    args = ap.parse_args()
    vault = os.path.abspath(args.vault)
    work = args.work or os.path.join(vault, ".recipe-import")
    cache = os.path.join(work, "cache")

    assignments = json.load(open(os.path.join(work, "folders.json"), encoding="utf-8"))["assignments"]
    written, skipped, noimg = 0, 0, []
    for rid, folder in assignments.items():
        cache_f = os.path.join(cache, rid + ".json")
        if not os.path.exists(cache_f):
            continue
        d = json.load(open(cache_f, encoding="utf-8"))
        folder_dir = os.path.join(vault, folder)
        fname, already = resolve_filename(folder_dir, slug_filename(d["name"]), d.get("author"), rid)
        if already:
            skipped += 1
            continue
        os.makedirs(folder_dir, exist_ok=True)
        if d.get("image"):
            os.makedirs(os.path.join(folder_dir, "attachments"), exist_ok=True)
            if not download(d["image"], os.path.join(folder_dir, "attachments", fname + ".jpg")):
                noimg.append(d["name"])
                d["image"] = None
        # newline="\n": the vault is pinned to LF (core.autocrlf false); without this,
        # Python text mode on Windows would translate \n -> \r\n and break that.
        with open(os.path.join(folder_dir, fname + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(build_note(d, folder, fname))
        written += 1

    print(f"written: {written}  skipped(existing): {skipped}  image-failed: {len(noimg)}")
    for n in noimg:
        print("  ! no image:", n)


if __name__ == "__main__":
    main()
