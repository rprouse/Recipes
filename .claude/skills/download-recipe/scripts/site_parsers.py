"""Per-host repair parsers for sites whose schema.org data is a stub.

`recipe_extract.py` leans on recipe-scrapers' generic schema.org path, which
works on essentially every recipe site. A few sites publish a Recipe node
carrying only name and image while keeping the actual recipe in page markup.
recipe-scrapers reports success on those and returns zero ingredients — a
silent failure, unlike the loud HTTP 403s other sites hand out.

A parser takes (html, data), where `data` is what the schema.org pass produced,
and returns a dict of fields to merge in. Contract:

  * return {"gated": True} if the page carries no recipe content (paywall)
  * fill only fields the schema.org pass left empty — never overwrite
  * never return an "image" key; see _parse_outdooreats for why
  * put non-standard extras under a "camping" sub-object
"""

import re
from urllib.parse import urlparse


def _soup(html):
    # Imported lazily so importing this module costs nothing when no parser runs.
    from bs4 import BeautifulSoup  # type: ignore[import-not-found]

    return BeautifulSoup(html, "html.parser")


NUMBERED_RE = re.compile(r"^\d+[.)]\s*")
# Every recipe closes with a sign-off: "EAT & PACK IT OUT" in its own <p>, or a
# bare "EAT!" as the last <li>. Matched whole, so a real step that merely starts
# with "Eat" ("Eat with crackers") is left alone.
SIGNOFF_RE = re.compile(r"^eat\s*!*$|^eat\s*&\s*pack it out\s*!*$", re.I)
GRAMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*g\b", re.I)
ML_RE = re.compile(r"(\d+(?:\.\d+)?)\s*ml\b", re.I)
OZ_RE = re.compile(r"(\d+(?:\.\d+)?)\s*oz\b", re.I)
WATER_RE = re.compile(r"^\s*water\b", re.I)
HEAT_RE = re.compile(r"\b(boil|burner|heat|simmer|stove|flame)\b", re.I)
BAG_RE = re.compile(r"\b(freezer bag|zip.?lock|pouch)\b", re.I)
STEEP_RE = re.compile(r"\b(just add|add hot water|steep)\b", re.I)


def _norm(s):
    """Collapse all whitespace runs to single spaces and strip."""
    return " ".join(s.split())


def _split_on_br(node):
    """Split a node's contents at <br> tags into normalized text fragments.

    Outdoor Eats writes every step into a single <p itemprop="recipeInstructions">
    separated by <br>, rather than using a list. Splitting on the tag (rather than
    on the rendered text) is what keeps the step boundaries intact.
    """
    parts, current = [], []
    for child in node.children:
        if getattr(child, "name", None) == "br":
            parts.append("".join(current))
            current = []
        else:
            current.append(child.get_text() if hasattr(child, "get_text") else str(child))
    parts.append("".join(current))
    return [_norm(p) for p in parts if _norm(p)]


def _steps_and_note(frags):
    """Split <br> fragments into (steps, cook's note).

    Steps carry their own "1. " numbering in the text, which is stripped. Three
    quirks, all real:

      * Some recipes repeat the "Steps" heading inside the <p>
        (chicken-dijon-with-rice does; hiker-pasta does not).
      * Only fragments after the LAST numbered step are a cook's note. On
        chicken-dijon they are the two <br>-wrapped halves of one sentence
        ("*you can also cook sauce separately, before or after" / "rice
        depending on your pot/pan sitch.") and would otherwise become bogus
        steps 6 and 7. They are rejoined and handed back for the tip callout.
      * An unnumbered fragment BETWEEN two numbered steps is a wrapped
        continuation of the step above it, not a note — sun-dried-tomato-tuna-mix
        splits step 1 across a <br> ("Chop or crush nuts/olives as needed").
        Position, not the absence of a number, is what separates the two cases.
    """
    last_numbered = max(
        (i for i, frag in enumerate(frags) if NUMBERED_RE.match(frag)), default=-1
    )
    steps, note = [], []
    for i, frag in enumerate(frags):
        if not steps and frag.strip().lower() == "steps":
            continue
        if NUMBERED_RE.match(frag):
            steps.append(NUMBERED_RE.sub("", frag).strip())
        elif not steps:
            continue  # An unnumbered fragment before any step is stray heading text.
        elif i < last_numbered:
            steps[-1] = _norm(f"{steps[-1]} {frag}")
        else:
            note.append(frag)
    return steps, _norm(" ".join(note))


def _ingredients(soup):
    """Ingredient lines from microdata, reading only the innermost node.

    An older template (bacon-cheddar-grits-w-eggs) nests the itemprop, writing
    `<li itemprop="recipeIngredient"><p itemprop="recipeIngredient">…</p></li>`.
    Both nodes match the selector and both render the same text, so taking every
    match lists each ingredient twice. A node wrapping another is the container,
    never a line of its own.
    """
    return [
        _norm(node.get_text(" "))
        for node in soup.select('[itemprop="recipeIngredient"]')
        if node.select_one('[itemprop="recipeIngredient"]') is None
    ]


def _list_steps(items):
    """Steps from <li itemprop="recipeInstructions"> nodes, in document order.

    The list supplies the numbering, so unlike the <p> shape there is nothing to
    key on but position. Any numbering repeated in the text is stripped so both
    variants come out the same.
    """
    steps = []
    for li in items:
        frag = NUMBERED_RE.sub("", _norm(li.get_text(" "))).strip()
        if frag and not SIGNOFF_RE.match(frag):
            steps.append(frag)
    return steps


def _instructions(soup):
    """Steps and note from whichever recipeInstructions node carries the recipe.

    Two markup shapes are in the wild. Most recipes write every step into one
    <p itemprop="recipeInstructions"> separated by <br>, numbered in the text;
    others (pad-thai) use an <ol> of <li itemprop="recipeInstructions">, where the
    list renders the numbering and the text carries none. Checking for the list
    first matters: scanning per-node would read a numbered first <li> as a
    complete one-step recipe and drop the rest.

    Within the <p> shape the site emits several `recipeInstructions` nodes and the
    numbered one is not reliably first. Every recipe ends with an "EAT & PACK IT
    OUT" sign-off in its own <p>, and a no-cook recipe LEADS with a banner
    paragraph ("*NO COOK / NO BURNER RECIPE*" on sun-dried-tomato-tuna-mix),
    pushing the steps into the middle. Selecting the node by what it contains —
    rather than by index — skips both without special-casing either.
    """
    items = soup.select('li[itemprop="recipeInstructions"]')
    if len(items) > 1:
        return _list_steps(items), ""

    for node in soup.select('[itemprop="recipeInstructions"]'):
        steps, note = _steps_and_note(_split_on_br(node))
        if steps:
            return steps, note
    return [], ""


def _digits(soup):
    """Map the stats block's visible labels to their values.

    Returns e.g. {"servings": "Yields 2", "minutes": "15",
                  "weight per serving": "~8.4 oz / ~238 g"}.
    Keyed on the label rather than position, so a reordered or added tile does
    not silently shift every value by one.
    """
    out = {}
    for item in soup.select(".recipe-digits-item"):
        label = _norm(item.select_one(".text").get_text(" ")) if item.select_one(".text") else ""
        value = _norm(item.select_one(".digits").get_text(" ")) if item.select_one(".digits") else ""
        if label:
            out[label.lower()] = value
    return out


def _grams(text):
    """Grams from a dual-unit weight string. '~8.4 oz / ~238 g' -> 238.

    The `~` estimate marker cannot survive a numeric field; these are
    approximations by nature. Requires the `g` unit, so the ounce figure is
    never mistaken for grams.
    """
    m = GRAMS_RE.search(text or "")
    return int(round(float(m.group(1)))) if m else None


def _water_ml(ingredients):
    """Millilitres of water the recipe needs.

    Returns 0 when no water ingredient exists (genuinely no water needed) and
    None when a water line exists but carries no parseable quantity (unknown).
    That distinction is load-bearing: in the note, 0 and blank mean different
    things when you are planning a dry camp.

    Where a range is given, the upper bound wins — under-packing water is the
    failure that actually hurts.
    """
    for ing in ingredients:
        if WATER_RE.match(ing):
            mls = [float(x) for x in ML_RE.findall(ing)]
            if mls:
                return int(round(max(mls)))
            ozs = [float(x) for x in OZ_RE.findall(ing)]
            if ozs:
                return int(round(max(ozs) * 29.5735))
            return None
    return 0


def _author(soup):
    """The recipe's author from microdata.

    Deliberately NOT `.recipe-subtitle`, which names the tester — on
    chicken-dijon-with-rice the author is Corso and the tester is Grammysaurus.
    They coincide on hiker-pasta, which makes conflating them an easy mistake.
    Also avoids the `.recipe-author` text, which renders unspaced as "byCorso".
    """
    node = soup.select_one('[itemprop="author"] [itemprop="name"]')
    return _norm(node.get_text(" ")) if node else None


def _dietary_tags(soup):
    """'High Calorie, Gluten Free, Nut Free' -> ['high-calorie', ...]."""
    node = soup.select_one(".fd-Recipe-Type")
    if not node:
        return []
    raw = _norm(node.get_text(" "))
    return [t.strip().lower().replace(" ", "-") for t in raw.split(",") if t.strip()]


def _cook_method(steps, water_ml, type_tags=()):
    """Infer how the meal is cooked. ALWAYS reported as inferred to the caller.

    The site publishes the answer for the one case that matters: its own type
    taxonomy (the same list `_dietary_tags` reads) labels no-burner recipes
    `No Cook`. That label is the author's, so it beats any reading of the step
    text and is checked first.

    Everything below it reads the steps, and `water_ml` corroborates: an
    unheated step list only means no-cook if the recipe needs no water either.
    Without that check an EMPTY step list — a parse failure — reports itself as a
    perfectly plausible no-cook recipe, which is how a broken import stays silent.

    Deliberately conservative otherwise: it falls through to one-pot, the
    commonest case on this site, rather than guessing cleverly at a distinction
    the step text does not reliably carry.
    """
    if "no-cook" in type_tags:
        return "no-cook"
    blob = " ".join(steps)
    if not HEAT_RE.search(blob):
        return "no-cook" if water_ml == 0 else "one-pot"
    if BAG_RE.search(blob):
        return "freezer-bag"
    if STEEP_RE.search(blob):
        return "boil-only"
    return "one-pot"


def _parse_outdooreats(html, data):
    """Recover a recipe from outdooreats.com page markup.

    The site's Recipe JSON-LD carries only name/author/image — no ingredients,
    steps, yield, or description. The real content is inline microdata
    (itemprop=...) plus a `.recipe-digits` stats block. Microdata is preferred
    over the theme's CSS classes: `itemprop` names are contractual, class names
    are a redesign away from changing.
    """
    soup = _soup(html)

    # A member-locked page has no recipe content at all — MemberPress replaces the
    # body with a signup pitch server-side. Unlike NYT, nothing is recoverable, so
    # detect it first and let the caller abort rather than write an empty note.
    if not soup.select('[itemprop="recipeIngredient"]'):
        return {"gated": True}

    ingredients = _ingredients(soup)
    steps, note = _instructions(soup)
    digits = _digits(soup)

    out = {
        "ingredients": ingredients,
        "instructions_list": steps,
        "cooks_note": note,
    }

    author = _author(soup)
    if author:
        out["author"] = author

    yield_node = soup.select_one('[itemprop="recipeYield"]')
    if yield_node:
        n = _norm(yield_node.get_text(" "))
        # Singular matters: this site is mostly single-serving recipes, and
        # SKILL.md tells the note writer to copy `yields` verbatim — so a sloppy
        # "1 servings" here lands in the finished note.
        out["yields"] = f"{n} {'serving' if n == '1' else 'servings'}" if n else None

    minutes = re.search(r"\d+", digits.get("minutes", ""))
    if minutes:
        out["total_time"] = int(minutes.group(0))

    title = soup.select_one(".recipe-title")
    if title:
        out["title"] = _norm(title.get_text(" "))

    water = _water_ml(ingredients)
    tags = _dietary_tags(soup)
    out["camping"] = {
        "weight_per_serving_g": _grams(digits.get("weight per serving", "")),
        "water_needed_ml": water,
        "cook_method": _cook_method(steps, water, tags),
        "cook_method_inferred": True,
        "dietary_tags": tags,
    }

    # NOTE: no "image" key, ever. The stub JSON-LD carries the correct recipe
    # photo; the page markup leads with the site logo (montYbocalogo.png), so any
    # scrape here would replace good data with the logo.
    return out


SITE_PARSERS = {"outdooreats.com": _parse_outdooreats}


def parser_for(url):
    """Return the repair parser for `url`'s host, or None. `www.` is ignored."""
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return SITE_PARSERS.get(host)
