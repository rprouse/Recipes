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
