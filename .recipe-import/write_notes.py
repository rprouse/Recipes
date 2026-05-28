"""
Write Obsidian recipe notes from cached recipe data + folder assignments.
Downloads each lead image into <Folder>/attachments/. Resumable: skips a recipe
whose note file already exists.

Usage: python write_notes.py
Reads: .recipe-import/cache/<id>.json, .recipe-import/folders.json
Writes: <Vault>/<Folder>/<Name>.md  and  <Vault>/<Folder>/attachments/<Name>.jpg
"""
import os, re, json, time, datetime, urllib.request, urllib.error

VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(VAULT, ".recipe-import")
CACHE = os.path.join(HERE, "cache")
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
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


def make_tags(folder, keywords, diet):
    tags = [folder.lower().replace(" ", "-")]
    for kw in (keywords or "").split(","):
        k = kw.strip().lower().replace(" ", "-")
        if k in DESCRIPTORS and k not in tags:
            tags.append(k)
    d = (diet or "").lower()
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


def build_note(d, folder):
    name = d["name"]
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
        body.append(f"![[attachments/{slug_filename(name)}.jpg]]")
    body.append(f"# {name}")
    if d.get("description"):
        body.append(d["description"])
    body.append("### 🛒 Ingredients\n" + "\n".join(f"- {i}" for i in d["ingredients"]))
    body.append("### 🥣 Steps\n" + "\n".join(f"{n}. {s}" for n, s in enumerate(d["steps"], 1)))
    if d.get("tip"):
        tip_lines = "\n".join(f"> {ln}" for ln in d["tip"].split("\n"))
        body.append(f"> [!tip] Tip\n{tip_lines}")
    return "\n\n".join(body) + "\n"


def main():
    assignments = json.load(open(os.path.join(HERE, "folders.json"), encoding="utf-8"))["assignments"]
    written, skipped, noimg = [], [], []
    for rid, folder in assignments.items():
        cache_f = os.path.join(CACHE, rid + ".json")
        if not os.path.exists(cache_f):
            continue
        d = json.load(open(cache_f, encoding="utf-8"))
        fname = slug_filename(d["name"])
        folder_dir = os.path.join(VAULT, folder)
        note_path = os.path.join(folder_dir, fname + ".md")
        if os.path.exists(note_path):
            skipped.append(d["name"])
            continue
        os.makedirs(folder_dir, exist_ok=True)
        if d.get("image"):
            os.makedirs(os.path.join(folder_dir, "attachments"), exist_ok=True)
            ok = download(d["image"], os.path.join(folder_dir, "attachments", fname + ".jpg"))
            if not ok:
                noimg.append(d["name"])
                d["image"] = None  # drop embed if download failed
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(build_note(d, folder))
        written.append(f"{folder}/{fname}.md")

    print(f"written: {len(written)}  skipped(existing): {len(skipped)}  image-failed: {len(noimg)}")
    for w in written:
        print("  +", w)
    if noimg:
        print("Image download failed (note written without image):")
        for n in noimg:
            print("  !", n)


if __name__ == "__main__":
    main()
