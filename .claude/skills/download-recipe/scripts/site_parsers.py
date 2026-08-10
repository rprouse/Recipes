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
GRAMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*g\b", re.I)
ML_RE = re.compile(r"(\d+(?:\.\d+)?)\s*ml\b", re.I)
OZ_RE = re.compile(r"(\d+(?:\.\d+)?)\s*oz\b", re.I)
WATER_RE = re.compile(r"^\s*water\b", re.I)


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

    Steps carry their own "1. " numbering in the text, which is stripped. Two
    quirks, both real:

      * Some recipes repeat the "Steps" heading inside the <p>
        (chicken-dijon-with-rice does; hiker-pasta does not).
      * Trailing UNNUMBERED fragments are a cook's note, not steps. On
        chicken-dijon they are the two <br>-wrapped halves of one sentence
        ("*you can also cook sauce separately, before or after" / "rice
        depending on your pot/pan sitch.") and would otherwise become bogus
        steps 6 and 7. They are rejoined and handed back for the tip callout.
    """
    steps, note = [], []
    for frag in frags:
        if not steps and frag.strip().lower() == "steps":
            continue
        if NUMBERED_RE.match(frag):
            steps.append(NUMBERED_RE.sub("", frag).strip())
        elif steps:
            note.append(frag)
        # An unnumbered fragment before any step is stray heading text — skipped.
    return steps, _norm(" ".join(note))


def _ingredients(soup):
    return [_norm(li.get_text(" ")) for li in soup.select('[itemprop="recipeIngredient"]')]


def _instructions(soup):
    """Steps and note from the FIRST recipeInstructions <p>.

    Taking only the first drops the "EAT & PACK IT OUT" sign-off, which the site
    puts in a second <p> — no special-casing needed.
    """
    nodes = soup.select('[itemprop="recipeInstructions"]')
    if not nodes:
        return [], ""
    return _steps_and_note(_split_on_br(nodes[0]))


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

    return {}


SITE_PARSERS = {"outdooreats.com": _parse_outdooreats}


def parser_for(url):
    """Return the repair parser for `url`'s host, or None. `www.` is ignored."""
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return SITE_PARSERS.get(host)
