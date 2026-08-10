# /// script
# requires-python = ">=3.10"
# dependencies = ["recipe-scrapers>=15.11", "beautifulsoup4"]
# ///
"""Extract a recipe from any cooking site into normalized JSON, and optionally
download its lead image.

Run with **uv** — the PEP 723 header above declares the dependency, so uv resolves
and caches `recipe-scrapers` on first run with no manual install:

    uv run .claude/skills/download-recipe/scripts/recipe_extract.py <url> \
        --out recipe.json \
        --image "G:/My Drive/Recipes/<Folder>/attachments/<Recipe Name>.jpg"

Why recipe-scrapers rather than a hand-rolled JSON-LD parser: it ships 620+
site-specific scrapers and falls back to generic schema.org for everything else,
so quirks (QuantitativeValue times, entity-encoded text, odd author shapes,
multi-crop images) are already handled in one place.

This script deliberately does NOT write the vault note. It emits data; the note is
authored with editorial judgment so tags, the overview paragraph, and the `time:`
phrasing match the vault's style.

Output JSON fields: title, author, yields, total_time, prep_time, cook_time (raw
ints, minutes), time_human, description, category, cuisine, keywords[],
dietary_restrictions, ingredients[], instructions_list[], image, site_name,
canonical_url, plus missing[] naming every field that could not be extracted and why.
"""

import argparse
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request

from site_parsers import parser_for


class Gated(Exception):
    """The page is behind a hard paywall with no recoverable content.

    Distinct from a fetch failure: the request succeeded, the page simply has no
    recipe in it. Callers must abort rather than write a half-empty note.
    """


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Fields read off the scraper. Each is called in isolation because
# recipe_scrapers._schemaorg raises SchemaOrgException for any absent field —
# without per-getter isolation, one missing `author` would abort the extraction.
FIELDS = (
    "title",
    "author",
    "yields",
    "total_time",
    "prep_time",
    "cook_time",
    "description",
    "category",
    "cuisine",
    "keywords",
    # Drives the vegan/vegetarian tags several notes carry (schema suitableForDiet).
    "dietary_restrictions",
    "ingredients",
    "instructions_list",
    "image",
    "site_name",
    "canonical_url",
)


def fetch(url, tries=6, cookie=None):
    """Fetch with a browser UA — many recipe CDNs refuse bare requests.

    Retries patiently with exponential backoff because Dotdash Meredith sites
    (Serious Eats, Simply Recipes, AllRecipes, Food & Wine) hand out **intermittent
    403s** to automated clients. This is rate-limiting, not fingerprinting: curl and
    urllib both see an unpredictable mix of 200 and 403 on the same URL seconds
    apart, so switching HTTP client does not help — only waiting does.
    """
    last = None
    for n in range(tries):
        try:
            headers = dict(HEADERS)
            if cookie:
                # Seam for Outdoor Eats Recipe Club membership. Nothing sets this yet —
                # the user holds no membership, so ~46% of that site stays unreachable and
                # the gate check in site_parsers handles it. When a session cookie does get
                # passed here, gated pages render in full and the existing parser handles
                # them unchanged.
                headers["Cookie"] = cookie
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            # HTTPError subclasses URLError, so 403/429/5xx all land here. Retry only
            # what can actually change: a 404/410 is permanent (usually a wrong URL),
            # so failing immediately beats burning 30s on a dead link.
            if isinstance(e, urllib.error.HTTPError) and e.code in (404, 410):
                raise RuntimeError(f"{url} returned {e.code} — check the URL") from e
            if n < tries - 1:
                wait = 2**n  # 1,2,4,8,16 -> ~31s total before giving up
                print(f"  {e} — retrying in {wait}s ({n + 1}/{tries})", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"could not fetch {url} after {tries} tries: {last}")


def humanize(minutes):
    """255 -> '4 hours 15 minutes'. The vault uses both this and a bare minute
    count, so the caller gets both and picks per recipe."""
    if not minutes or not isinstance(minutes, int):
        return ""
    h, m = divmod(minutes, 60)
    parts = []
    if h:
        parts.append(f"{h} hour" + ("s" if h != 1 else ""))
    if m:
        parts.append(f"{m} minutes")
    return " ".join(parts) or "0 minutes"


def og_image(html):
    """Recover a lead photo when schema.org carries none.

    Some recipes ship a null JSON-LD `image` (NYT does this — e.g.
    1024405-saag-shrimp). The `image:` frontmatter property drives the card views
    in All Recipes.base and Make Again.base, so a note without one renders a blank
    card; recovering it from og:image is worth the six lines. Where a larger 16:9
    crop of the same asset is present in the HTML, prefer it — confirmed by
    scraping the page, not by guessing a filename.
    """
    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html) or re.search(
        r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html
    )
    if not m:
        return None
    og = m.group(1)
    asset = og.rsplit("/", 1)[0]
    bigger = re.findall(
        re.escape(asset) + r"/[^\"']*videoSixteenByNineJumbo1600[^\"']*\.jpg", html
    )
    return bigger[0] if bigger else og


def image_dims(b):
    """(width, height) for PNG/JPEG from raw bytes — no Pillow needed.

    Worth reporting: it distinguishes the intended large crop from a thumbnail.
    """
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
    if b[:2] == b"\xff\xd8":
        i = 2
        while i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            marker = b[i + 1]
            # SOF0..SOF15 (minus the non-frame DHT/JPG/DAC markers) carry the size
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                return int.from_bytes(b[i + 7 : i + 9], "big"), int.from_bytes(b[i + 5 : i + 7], "big")
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = int.from_bytes(b[i + 2 : i + 4], "big")
            if seg <= 0:
                break
            i += 2 + seg
    return None, None


def image_format(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:2] == b"\xff\xd8":
        return "jpeg"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def merge_recovered(data, recovered, missing):
    """Merge a site parser's fields into `data`; record BOTH outcomes in missing[].

    Only fields the schema.org pass left empty are filled — the standard data is
    trusted first, exactly as with the og:image recovery above.

    Recording the misses is the point. A parser that hands back an empty value for
    a field `data` also lacks used to leave no trace at all: not merged, not
    listed, no error — an import that reports success while returning nothing. That
    is the silent failure this whole repair path exists to prevent, so a miss now
    says so in missing[]. Either outcome replaces the field's earlier entry, so the
    array always names the last thing that happened to that field.

    Scoped deliberately: the caller runs this only for hosts that HAVE a repair
    parser, so no other site's missing[] changes shape.
    """
    for key, value in recovered.items():
        if data.get(key):
            continue
        if value:
            data[key] = value
            why = "recovered from site parser"
        else:
            why = "site parser found nothing"
        missing = [m for m in missing if m["field"] != key]
        missing.append({"field": key, "error": why})
    return missing


def extract(url, html, best_image=False):
    # Resolved by uv from the PEP 723 header, so it is absent from the system
    # interpreter — a linter "unresolved import" here is expected, not a fault.
    from recipe_scrapers import scrape_html  # type: ignore[import-not-found]

    # supported_only=False -> use the generic schema.org path on unregistered
    # sites too (`wild_mode` is deprecated).
    #
    # best_image defaults to False on purpose. It selects by raw pixel count, which
    # on NYT returns the 1800x1800 mediumSquareAt3X crop over the 1600x900
    # videoSixteenByNineJumbo1600 hero. The 851 existing NYT notes all use the 16:9
    # landscape, and leaving the flag off yields the site's own primary crop — the
    # landscape one. Serious Eats returns the same URL either way.
    scraper = scrape_html(html, org_url=url, supported_only=False, best_image=best_image)

    data, missing = {}, []
    for name in FIELDS:
        try:
            data[name] = getattr(scraper, name)()
        except Exception as e:  # noqa: BLE001 — one bad field must not kill the run
            data[name] = None
            missing.append({"field": name, "error": type(e).__name__})

    if not data.get("image"):
        recovered = og_image(html)
        if recovered:
            data["image"] = recovered
            missing = [m for m in missing if m["field"] != "image"]
            missing.append({"field": "image", "error": "recovered from og:image"})

    # Repair pass for sites whose schema.org Recipe node is a stub. Sits here, after
    # the schema.org pass, for the same reason the og:image recovery above does:
    # trust the standard data first, patch only what it failed to provide.
    parser = parser_for(url)
    if parser:
        recovered = parser(html, data)
        if recovered.get("gated"):
            raise Gated(
                "recipe is member-gated (Outdoor Eats Recipe Club) — no content in page"
            )
        # Pulled out before the merge below: neither is a schema.org field, so
        # neither belongs in missing[] — that array tracks what the standard pass
        # failed to find, and listing extras there would be noise.
        camping = recovered.pop("camping", None)
        cooks_note = recovered.pop("cooks_note", None)
        missing = merge_recovered(data, recovered, missing)
        if camping:
            data["camping"] = camping
        if cooks_note:
            data["cooks_note"] = cooks_note

    data["time_human"] = humanize(data.get("total_time"))
    data["url"] = url
    data["missing"] = missing
    return data


def save_image(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        blob = r.read()
    if len(blob) < 1000:
        return {"ok": False, "why": f"suspiciously small ({len(blob)} bytes)"}
    fmt = image_format(blob)
    if not fmt:
        return {"ok": False, "why": "not a recognized image (bad magic bytes)"}
    w, h = image_dims(blob)
    with open(dest, "wb") as f:
        f.write(blob)
    return {"ok": True, "path": dest, "bytes": len(blob), "format": fmt, "width": w, "height": h}


def main():
    # Recipe text is UTF-8 (curly quotes, ½ ¼). Without this the Windows console
    # mangles the summary and error messages; the JSON file is unaffected either way.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Extract a recipe into normalized JSON.")
    ap.add_argument("url")
    ap.add_argument("--out", help="write the JSON here (default: stdout)")
    ap.add_argument("--image", help="download the lead image to this exact path")
    ap.add_argument("--save-html", help="also keep the fetched HTML here (debugging)")
    ap.add_argument(
        "--best-image",
        action="store_true",
        help="pick the highest-pixel-count crop instead of the site's primary one "
        "(on NYT this returns a square crop rather than the 16:9 hero)",
    )
    args = ap.parse_args()

    html = fetch(args.url)
    if args.save_html:
        with open(args.save_html, "w", encoding="utf-8") as f:
            f.write(html)

    try:
        data = extract(args.url, html, best_image=args.best_image)
    except Gated as e:
        print(f"GATED: {e}", file=sys.stderr)
        print("No JSON written. Free recipes only — this one needs a membership.", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        sys.exit(f"extraction failed: {type(e).__name__}: {e}")

    if args.image:
        if data.get("image"):
            data["image_download"] = save_image(data["image"], args.image)
        else:
            data["image_download"] = {"ok": False, "why": "page exposed no image"}

    payload = json.dumps(data, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
    else:
        print(payload)
        return

    # Console summary. UTF-8 is reconfigured above, but never judge the extracted
    # text by this preview — trust the JSON file's bytes.
    print(f"title       : {data.get('title')}")
    print(f"author      : {data.get('author')}")
    print(f"yields      : {data.get('yields')}")
    print(
        f"time        : total={data.get('total_time')} prep={data.get('prep_time')} "
        f"cook={data.get('cook_time')}  -> {data.get('time_human')!r}"
    )
    print(f"category    : {data.get('category')}   cuisine: {data.get('cuisine')}")
    print(f"keywords    : {data.get('keywords')}")
    print(f"diet        : {data.get('dietary_restrictions')}")
    print(f"ingredients : {len(data.get('ingredients') or [])}")
    print(f"steps       : {len(data.get('instructions_list') or [])}")
    print(f"image       : {data.get('image')}")
    if "image_download" in data:
        print(f"downloaded  : {data['image_download']}")
    print(f"missing     : {data['missing'] or 'nothing'}")
    print(f"wrote       : {args.out}")


if __name__ == "__main__":
    sys.exit(main() or 0)
