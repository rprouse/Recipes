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
