# Camping Recipes (Outdoor Eats) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import recipes from outdooreats.com into a new `Camping/` folder, capturing pack weight, water, and cook method, without breaking the extractor every other site depends on.

**Architecture:** A new `site_parsers.py` module holds per-host repair parsers for sites whose `schema.org` data is a stub. `recipe_extract.py` consults it by hostname immediately after its schema.org pass, at the same seam where `og_image()` recovery already lives. Outdoor Eats' parser reads the page's inline **microdata** (`itemprop=...`), which is more stable than theme CSS classes. Camping-only data is returned under a `camping` sub-object so nothing else sees it.

**Tech Stack:** Python 3.10+, run via `uv run` with PEP 723 inline dependency headers. `beautifulsoup4` for parsing, `pytest` for tests. No repo-wide test config — the test file declares its own dependencies and runs standalone.

## Global Constraints

- **Run Python with `python`, never `python3`** — `python3` is the Microsoft Store stub on this machine and aborts. `uv run` handles the script's own interpreter.
- **Line endings are LF.** The vault pins `core.autocrlf false` / `core.eol lf`. Verify with a Python `\r` byte-count, never `grep -c $'\r'` (it false-positives on these UTF-8 notes).
- **Do not commit.** `CLAUDE.md` states the user commits via the obsidian-git keybindings. Commit commands appear in this plan as clearly-marked OPTIONAL steps; the default is to leave changes uncommitted. This intentionally overrides the writing-plans skill's "frequent commits" default, per the project instruction.
- **Never touch the `image` field in a site parser.** The stub JSON-LD carries the correct recipe photo; the site logo (`montYbocalogo.png`) appears earlier in the markup and any loose URL regex grabs it instead.
- **Images from this site are 800×800 PNG** — attachment, `image:` property, and embed all use `.png`.
- **UTF-8 everywhere.** The Windows console may render `½`, `é`, and em-dashes as `?`/`�` while the file bytes are correct. Trust the file, not the console.
- **`<scratch>` in this plan means** `C:/Users/ROBPRO~1/AppData/Local/Temp/claude/G--My-Drive-Recipes/c32e9e38-9905-4267-a57b-dfb417295497/scratchpad`. Substitute it literally; never write scratch files into the vault, which syncs to Google Drive.
- All paths are relative to the vault root, `G:/My Drive/Recipes`.
- Spec: `.claude/specs/2026-08-10-camping-recipes-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `.claude/skills/download-recipe/scripts/site_parsers.py` | **Create.** Per-host repair parsers + `parser_for(url)` lookup. All Outdoor Eats knowledge lives here. |
| `.claude/skills/download-recipe/scripts/test_site_parsers.py` | **Create.** Unit tests against hand-written HTML fixtures. Runs offline. |
| `.claude/skills/download-recipe/scripts/recipe_extract.py` | **Modify.** Add the `SITE_PARSERS` hook, the `Gated` exception, and `beautifulsoup4` to the PEP 723 header. |
| `Templates/Camping Recipe.md` | **Create.** Camping note template. |
| `Camping.base` | **Create.** Base with cards + weight table + no-cook views. |
| `Camping/Hiker Pasta.md`, `Camping/Chicken Dijon with Rice.md` | **Create.** The two proof notes, plus `Camping/attachments/*.png`. |
| `.claude/skills/download-recipe/SKILL.md` | **Modify.** Folder list, rule 0, Outdoor Eats subsection, paywall correction. |
| `CLAUDE.md` | **Modify.** Folder taxonomy, camping template, PNG note. |

Splitting `site_parsers.py` out rather than growing `recipe_extract.py` (293 lines) keeps each file to one responsibility: `recipe_extract.py` owns fetch/normalize/image, `site_parsers.py` owns per-site repair. Sibling imports work under `uv run` — verified.

---

### Task 1: Module scaffold and gate detection

Gate detection is the highest-risk behaviour: getting it wrong means writing empty notes. It also proves the sibling-import plumbing before any real parsing depends on it.

**Files:**
- Create: `.claude/skills/download-recipe/scripts/site_parsers.py`
- Test: `.claude/skills/download-recipe/scripts/test_site_parsers.py`

**Interfaces:**
- Consumes: nothing
- Produces: `parser_for(url) -> callable | None`; `_parse_outdooreats(html, data) -> dict`; the sentinel `{"gated": True}`

- [ ] **Step 1: Write the failing test**

Create `.claude/skills/download-recipe/scripts/test_site_parsers.py`:

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["beautifulsoup4", "pytest"]
# ///
"""Unit tests for site_parsers, run offline against hand-written fixtures.

Fixtures are minimal HTML reproducing the exact structures found on
outdooreats.com on 2026-08-10 — inline microdata plus the theme's
`.recipe-digits` block. They are hand-written rather than saved pages so the
tests stay small and state precisely which markup each behaviour depends on.
"""
import site_parsers


GATED_HTML = """
<html><body>
  <h1>BLTA Grain Bowl</h1>
  <div class="mepr-unauthorized">
    <h2>Join the Outdoor Eats Recipe Club</h2>
    <p>Get access to all 300+ recipes.</p>
  </div>
</body></html>
"""


def test_parser_for_resolves_outdooreats():
    assert site_parsers.parser_for("https://outdooreats.com/recipe/hiker-pasta/") is not None


def test_parser_for_ignores_www_prefix():
    assert site_parsers.parser_for("https://www.outdooreats.com/recipe/hiker-pasta/") is not None


def test_parser_for_returns_none_for_other_hosts():
    assert site_parsers.parser_for("https://cooking.nytimes.com/recipes/1234-thing") is None
    assert site_parsers.parser_for("https://www.seriouseats.com/some-recipe") is None


def test_gated_page_reports_gated():
    assert site_parsers._parse_outdooreats(GATED_HTML, {}) == {"gated": True}


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: FAIL — `ModuleNotFoundError: No module named 'site_parsers'`

- [ ] **Step 3: Write minimal implementation**

Create `.claude/skills/download-recipe/scripts/site_parsers.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: PASS, 4 passed

- [ ] **Step 5: (OPTIONAL) Commit** — default is to leave uncommitted; run only if the user asks.

```powershell
git add ".claude/skills/download-recipe/scripts/site_parsers.py" ".claude/skills/download-recipe/scripts/test_site_parsers.py"
git commit -m "feat: add site_parsers module with Outdoor Eats gate detection"
```

---

### Task 2: Ingredients, steps, and the cook's note

The trickiest parsing in the project. Steps are one `<br>`-separated blob, and trailing unnumbered fragments are a note, not steps.

**Files:**
- Modify: `.claude/skills/download-recipe/scripts/site_parsers.py`
- Test: `.claude/skills/download-recipe/scripts/test_site_parsers.py`

**Interfaces:**
- Consumes: `_soup()` from Task 1
- Produces: `_split_on_br(node) -> list[str]`; `_steps_and_note(frags) -> tuple[list[str], str]`

- [ ] **Step 1: Write the failing test**

Append to `test_site_parsers.py`, above the `__main__` block:

```python
# Hiker Pasta: every step numbered, no trailing note, sign-off in a second <p>.
HIKER_STEPS_HTML = """
<div class="recipe-instructions">
  <p itemprop="recipeInstructions">1. Slice snack sticks/tomatoes as needed<br/>2. Combine all ingredients except water. Stir<br/>3. TURN ON BURNER: HIGH HEAT<br/>4. Boil. HEAT TO MED<br/>5. Add pasta<br/>6. Cook until soft<br/>7. Garnish with crisps</p>
  <p itemprop="recipeInstructions">EAT &amp; PACK IT OUT</p>
</div>
"""

# Chicken Dijon: repeats the "Steps" heading inside the <p>, and ends with two
# unnumbered fragments that are the wrapped halves of one cook's note.
DIJON_STEPS_HTML = """
<div class="recipe-instructions">
  <p itemprop="recipeInstructions">Steps<br/>1. TURN ON BURNER: HIGH HEAT<br/>2. Add chicken, water, packet, salt<br/>3. Stir. Boil<br/>4. Add rice. Stir. Cover. Sit 10 min<br/>5. Fluff rice. Squirt mustard Squeeze lemon. Stir<br/>*you can also cook sauce separately, before or after<br/>rice depending on your pot/pan sitch.</p>
  <p itemprop="recipeInstructions">EAT &amp; PACK IT OUT</p>
</div>
"""

INGREDIENTS_HTML = """
<div class="recipe-ingredients-wrap"><h2>Ingredients</h2><ul>
  <li itemprop="recipeIngredient">Packaged Chicken - 9 oz / 275 g</li>
  <li itemprop="recipeIngredient">Water - 8 oz / 250 ml</li>
  <li itemprop="recipeIngredient">Instant Rice - 1 C / 150 g</li>
</ul></div>
"""


def _first_instructions(html):
    return site_parsers._soup(html).select('[itemprop="recipeInstructions"]')[0]


def test_split_on_br_returns_one_fragment_per_line():
    frags = site_parsers._split_on_br(_first_instructions(HIKER_STEPS_HTML))
    assert len(frags) == 7
    assert frags[0] == "1. Slice snack sticks/tomatoes as needed"
    assert frags[-1] == "7. Garnish with crisps"


def test_steps_are_numbered_stripped_and_note_empty():
    steps, note = site_parsers._steps_and_note(
        site_parsers._split_on_br(_first_instructions(HIKER_STEPS_HTML))
    )
    assert steps[0] == "Slice snack sticks/tomatoes as needed"
    assert len(steps) == 7
    assert note == ""


def test_leading_steps_heading_is_dropped():
    steps, _ = site_parsers._steps_and_note(
        site_parsers._split_on_br(_first_instructions(DIJON_STEPS_HTML))
    )
    assert len(steps) == 5
    assert steps[0] == "TURN ON BURNER: HIGH HEAT"


def test_trailing_unnumbered_fragments_become_the_note_not_steps():
    steps, note = site_parsers._steps_and_note(
        site_parsers._split_on_br(_first_instructions(DIJON_STEPS_HTML))
    )
    assert len(steps) == 5, "the note must not be counted as steps 6 and 7"
    assert note == (
        "*you can also cook sauce separately, before or after "
        "rice depending on your pot/pan sitch."
    )


def test_signoff_paragraph_is_excluded():
    steps, note = site_parsers._steps_and_note(
        site_parsers._split_on_br(_first_instructions(HIKER_STEPS_HTML))
    )
    assert "EAT & PACK IT OUT" not in " ".join(steps)
    assert "EAT & PACK IT OUT" not in note


def test_ingredients_read_from_microdata():
    got = site_parsers._ingredients(site_parsers._soup(INGREDIENTS_HTML))
    assert got == [
        "Packaged Chicken - 9 oz / 275 g",
        "Water - 8 oz / 250 ml",
        "Instant Rice - 1 C / 150 g",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: FAIL — `AttributeError: module 'site_parsers' has no attribute '_split_on_br'`

- [ ] **Step 3: Write minimal implementation**

Add to `site_parsers.py`, above `_parse_outdooreats`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: PASS, 10 passed

- [ ] **Step 5: (OPTIONAL) Commit** — only if the user asks.

```powershell
git add ".claude/skills/download-recipe/scripts/"
git commit -m "feat: parse Outdoor Eats ingredients, steps, and cook's note"
```

---

### Task 3: Stats block — servings, time, weight, water, author

**Files:**
- Modify: `.claude/skills/download-recipe/scripts/site_parsers.py`
- Test: `.claude/skills/download-recipe/scripts/test_site_parsers.py`

**Interfaces:**
- Consumes: `_norm`, `_soup`, `_ingredients` from Tasks 1–2
- Produces: `_digits(soup) -> dict[str, str]`; `_grams(text) -> int | None`; `_water_ml(ingredients) -> int | None`; `_author(soup) -> str | None`

- [ ] **Step 1: Write the failing test**

Append to `test_site_parsers.py`:

```python
DIGITS_HTML = """
<div class="recipe-digits">
  <div class="recipe-digits-item">
    <div class="digits"><span class="meta-label">Yields</span>
      <span class="meta-servings"><span itemprop="recipeYield">2</span></span></div>
    <div class="text">Servings</div>
  </div>
  <div class="recipe-digits-item">
    <div class="digits"><span class="fd-Ingredient"></span></div>
    <div class="text">Ingredients</div>
  </div>
  <div class="recipe-digits-item">
    <div class="digits text-minutes"><span class="meta-label"></span><span>15</span></div>
    <div class="text">Minutes</div>
  </div>
  <div class="recipe-digits-item">
    <div class="digits text-description"><div itemprop="description"><p>~8.4 oz / ~238 g</p></div></div>
    <div class="text">Weight per serving</div>
  </div>
</div>
"""

AUTHOR_HTML = """
<p class="recipe-author">by <strong itemprop="author" itemscope itemtype="http://schema.org/Person">
  <span itemprop="name">Corso</span></strong></p>
<div class="recipe-subtitle">Tested by<span>Grammysaurus</span></div>
"""


def test_digits_keyed_by_visible_label():
    d = site_parsers._digits(site_parsers._soup(DIGITS_HTML))
    assert d["minutes"] == "15"
    assert d["weight per serving"] == "~8.4 oz / ~238 g"


def test_grams_parsed_ignoring_tilde_and_ounces():
    assert site_parsers._grams("~8.4 oz / ~238 g") == 238
    assert site_parsers._grams("~10 oz / ~275 g") == 275


def test_grams_returns_none_when_absent():
    assert site_parsers._grams("a handful") is None


def test_water_ml_from_ingredient_line():
    assert site_parsers._water_ml(["Water - 8 oz / 250 ml", "Salt - to taste"]) == 250


def test_water_range_takes_upper_bound():
    # Hiker Pasta lists "8-12 oz / 400 ml"; under-packing water is the failure
    # that matters, so a range resolves upward.
    assert site_parsers._water_ml(["Water - 8-12 oz / 400 ml"]) == 400


def test_water_zero_when_no_water_ingredient():
    # 0 means "genuinely needs no water"; None would mean "unknown".
    assert site_parsers._water_ml(["Tortilla - 1", "Cheese - 2 oz / 56 g"]) == 0


def test_author_from_microdata_not_the_by_prefix():
    assert site_parsers._author(site_parsers._soup(AUTHOR_HTML)) == "Corso"


def test_author_is_not_the_tester():
    # .recipe-subtitle names the tester (Grammysaurus), who differs from the
    # author (Corso) on chicken-dijon-with-rice. They must not be conflated.
    assert site_parsers._author(site_parsers._soup(AUTHOR_HTML)) != "Grammysaurus"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: FAIL — `AttributeError: module 'site_parsers' has no attribute '_digits'`

- [ ] **Step 3: Write minimal implementation**

Add to `site_parsers.py`:

```python
GRAMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*g\b", re.I)
ML_RE = re.compile(r"(\d+(?:\.\d+)?)\s*ml\b", re.I)
OZ_RE = re.compile(r"(\d+(?:\.\d+)?)\s*oz\b", re.I)
WATER_RE = re.compile(r"^\s*water\b", re.I)


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: PASS, 18 passed

- [ ] **Step 5: (OPTIONAL) Commit** — only if the user asks.

---

### Task 4: Cook method, dietary types, and full parser assembly

**Files:**
- Modify: `.claude/skills/download-recipe/scripts/site_parsers.py`
- Test: `.claude/skills/download-recipe/scripts/test_site_parsers.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3
- Produces: `_cook_method(steps, water_ml) -> str`; `_dietary_tags(soup) -> list[str]`; a fully populated `_parse_outdooreats` returning `{title, author, yields, total_time, ingredients, instructions_list, description, camping: {...}, cooks_note}`

- [ ] **Step 1: Write the failing test**

Append to `test_site_parsers.py`:

```python
TYPES_HTML = """
<div class="fd-recipe-type-cont"><span class="fd-Recipe-Type">High Calorie, Gluten Free, Nut Free</span></div>
"""

FULL_HTML = f"""
<html><body>
  <h1 class="recipe-title">Chicken Dijon with Rice</h1>
  {INGREDIENTS_HTML}
  {DIJON_STEPS_HTML}
  {DIGITS_HTML}
  {TYPES_HTML}
  {AUTHOR_HTML}
</body></html>
"""


def test_dietary_types_become_kebab_case_tags():
    got = site_parsers._dietary_tags(site_parsers._soup(TYPES_HTML))
    assert got == ["high-calorie", "gluten-free", "nut-free"]


def test_cook_method_one_pot_when_ingredients_cook_in_the_pot():
    steps = ["TURN ON BURNER: HIGH HEAT", "Add chicken, water, packet, salt",
             "Stir. Boil", "Add rice. Stir. Cover. Sit 10 min"]
    assert site_parsers._cook_method(steps, 250) == "one-pot"


def test_cook_method_no_cook_when_nothing_is_heated():
    steps = ["Combine everything in the tortilla", "Roll and eat"]
    assert site_parsers._cook_method(steps, 0) == "no-cook"


def test_cook_method_freezer_bag():
    steps = ["Boil water", "Pour into the freezer bag and seal", "Wait 10 min"]
    assert site_parsers._cook_method(steps, 300) == "freezer-bag"


def test_cook_method_boil_only():
    steps = ["Boil water", "Just add hot water and steep 5 min"]
    assert site_parsers._cook_method(steps, 250) == "boil-only"


def test_full_parse_populates_every_field():
    got = site_parsers._parse_outdooreats(FULL_HTML, {})
    assert got["author"] == "Corso"
    assert got["yields"] == "2 servings"
    assert got["total_time"] == 15
    assert len(got["ingredients"]) == 3
    assert len(got["instructions_list"]) == 5
    assert got["camping"]["weight_per_serving_g"] == 238
    assert got["camping"]["water_needed_ml"] == 250
    assert got["camping"]["cook_method"] == "one-pot"
    assert got["camping"]["dietary_tags"] == ["high-calorie", "gluten-free", "nut-free"]
    assert got["cooks_note"].startswith("*you can also cook sauce separately")


def test_full_parse_never_returns_an_image_key():
    # The stub JSON-LD has the right photo; the page markup leads with the site
    # logo (montYbocalogo.png). Returning an image here would overwrite good
    # data with the logo.
    assert "image" not in site_parsers._parse_outdooreats(FULL_HTML, {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: FAIL — `AttributeError: module 'site_parsers' has no attribute '_dietary_tags'`

- [ ] **Step 3: Write minimal implementation**

Add to `site_parsers.py`, and replace the stub body of `_parse_outdooreats`:

```python
HEAT_RE = re.compile(r"\b(boil|burner|heat|simmer|stove|flame)\b", re.I)
BAG_RE = re.compile(r"\b(freezer bag|zip.?lock|pouch)\b", re.I)
STEEP_RE = re.compile(r"\b(just add|add hot water|steep)\b", re.I)


def _dietary_tags(soup):
    """'High Calorie, Gluten Free, Nut Free' -> ['high-calorie', ...]."""
    node = soup.select_one(".fd-Recipe-Type")
    if not node:
        return []
    raw = _norm(node.get_text(" "))
    return [t.strip().lower().replace(" ", "-") for t in raw.split(",") if t.strip()]


def _cook_method(steps, water_ml):
    """Infer how the meal is cooked. ALWAYS reported as inferred to the caller.

    Deliberately conservative: it falls through to one-pot, the commonest case
    on this site, rather than guessing cleverly at a distinction the step text
    does not reliably carry.
    """
    blob = " ".join(steps)
    if not HEAT_RE.search(blob):
        return "no-cook"
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
        out["yields"] = f"{n} servings" if n else None

    minutes = re.search(r"\d+", digits.get("minutes", ""))
    if minutes:
        out["total_time"] = int(minutes.group(0))

    title = soup.select_one(".recipe-title")
    if title:
        out["title"] = _norm(title.get_text(" "))

    water = _water_ml(ingredients)
    out["camping"] = {
        "weight_per_serving_g": _grams(digits.get("weight per serving", "")),
        "water_needed_ml": water,
        "cook_method": _cook_method(steps, water),
        "cook_method_inferred": True,
        "dietary_tags": _dietary_tags(soup),
    }

    # NOTE: no "image" key, ever. The stub JSON-LD carries the correct recipe
    # photo; the page markup leads with the site logo (montYbocalogo.png), so any
    # scrape here would replace good data with the logo.
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: PASS, 25 passed

- [ ] **Step 5: (OPTIONAL) Commit** — only if the user asks.

---

### Task 5: Wire the hook into recipe_extract.py

The regression risk lives here: this file serves every other site in the vault.

**Files:**
- Modify: `.claude/skills/download-recipe/scripts/recipe_extract.py` (PEP 723 header ~line 1-4; `extract()` ~line 201-211; `main()`)

**Interfaces:**
- Consumes: `parser_for` from Task 1, `_parse_outdooreats` output shape from Task 4
- Produces: `Gated` exception; `data["camping"]`, `data["cooks_note"]` in the emitted JSON

- [ ] **Step 1: Capture a pre-change regression baseline**

Run, and keep both files — Task 5 Step 6 diffs against them:

```bash
uv run ".claude/skills/download-recipe/scripts/recipe_extract.py" \
  "https://cooking.nytimes.com/recipes/767821616-chicken-and-white-bean-stew" \
  --out "<scratch>/baseline-nyt.json"
uv run ".claude/skills/download-recipe/scripts/recipe_extract.py" \
  "https://www.onceuponachef.com/recipes/grilled-moroccan-chicken.html" \
  --out "<scratch>/baseline-ouac.json"
```

The second leg is **Once Upon a Chef**, not Serious Eats. Any non-outdooreats host proves the same thing — that `parser_for` is a strict no-op elsewhere — and Serious Eats is a Dotdash Meredith site that returns intermittent HTTP 403s to automated clients, which makes it a poor gate to block a task on. (Verified 2026-08-10: a valid Serious Eats URL taken from an existing vault note still 403'd after all 6 retries.) Try Serious Eats opportunistically if you like, but do not let it block the task; record it as unreachable and move on.

- [ ] **Step 2: Add `beautifulsoup4` to the PEP 723 header**

Replace lines 1-4 of `recipe_extract.py`:

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["recipe-scrapers>=15.11", "beautifulsoup4"]
# ///
```

bs4 already arrives transitively via recipe-scrapers (4.15.0); this makes the direct dependency explicit rather than inherited.

- [ ] **Step 3: Add the `Gated` exception and the import**

Near the top of `recipe_extract.py`, after the existing imports:

```python
from site_parsers import parser_for


class Gated(Exception):
    """The page is behind a hard paywall with no recoverable content.

    Distinct from a fetch failure: the request succeeded, the page simply has no
    recipe in it. Callers must abort rather than write a half-empty note.
    """
```

- [ ] **Step 4: Add the hook in `extract()`**

In `extract()`, immediately after the existing `og_image` recovery block (the one ending `missing.append({"field": "image", "error": "recovered from og:image"})`) and before `data["time_human"] = ...`:

```python
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
        # Pulled out before the merge loop below: neither is a schema.org field, so
        # neither belongs in missing[] — that array tracks what the standard pass
        # failed to find, and listing extras there would be noise.
        camping = recovered.pop("camping", None)
        cooks_note = recovered.pop("cooks_note", None)
        for key, value in recovered.items():
            if value and not data.get(key):
                data[key] = value
                missing = [m for m in missing if m["field"] != key]
                missing.append({"field": key, "error": "recovered from site parser"})
        if camping:
            data["camping"] = camping
        if cooks_note:
            data["cooks_note"] = cooks_note
```

- [ ] **Step 5: Handle `Gated` in `main()`**

Wrap the `extract(...)` call in `main()` so a gated page exits non-zero and writes nothing:

```python
    try:
        data = extract(url, html, best_image=args.best_image)
    except Gated as e:
        print(f"GATED: {e}", file=sys.stderr)
        print("No JSON written. Free recipes only — this one needs a membership.", file=sys.stderr)
        return 2
```

Confirm `main()`'s return value reaches `sys.exit()`; if it is called bare at the bottom of the file, change that line to `sys.exit(main() or 0)`.

- [ ] **Step 6: Thread the (unused) cookie parameter through `fetch()`**

The spec calls for an auth seam so membership support is later a small change rather than a rewrite. Keep it to exactly this — a parameter nothing currently sets. Change `fetch()`'s signature and its request construction:

```python
def fetch(url, tries=6, cookie=None):
    ...
    headers = {"User-Agent": UA}
    if cookie:
        # Seam for Outdoor Eats Recipe Club membership. Nothing sets this yet —
        # the user holds no membership, so ~46% of that site stays unreachable and
        # the gate check in site_parsers handles it. When a session cookie does get
        # passed here, gated pages render in full and the existing parser handles
        # them unchanged.
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
```

Deliberately unexercised by the test suite: there is no membership to test against, and a test asserting an unused parameter is passed through would only restate the implementation. It is three lines and reversible.

- [ ] **Step 7: Verify the new path, the gate, and no regression**

```bash
# free recipe -> full data
uv run ".claude/skills/download-recipe/scripts/recipe_extract.py" \
  "https://outdooreats.com/recipe/hiker-pasta/" --out "<scratch>/hiker.json"
```
Expected: `ingredients : 11`, `steps : 7`, and a `camping` block with `weight_per_serving_g: 275`, `water_needed_ml: 400`, `cook_method: one-pot`.

```bash
# gated recipe -> exit 2, no file
uv run ".claude/skills/download-recipe/scripts/recipe_extract.py" \
  "https://outdooreats.com/recipe/blta-grain-bowl/" --out "<scratch>/should-not-exist.json"
echo "exit=$?"
test ! -f "<scratch>/should-not-exist.json" && echo "OK: no file written"
```
Expected: `GATED: ...`, `exit=2`, `OK: no file written`.

```bash
# regression: other sites unchanged
uv run ".claude/skills/download-recipe/scripts/recipe_extract.py" \
  "https://cooking.nytimes.com/recipes/767821616-chicken-and-white-bean-stew" \
  --out "<scratch>/after-nyt.json"
python -c "import json,sys; a=json.load(open(sys.argv[1])); b=json.load(open(sys.argv[2])); print('IDENTICAL' if a==b else 'DIFFERS'); print([k for k in set(a)|set(b) if a.get(k)!=b.get(k)])" "<scratch>/baseline-nyt.json" "<scratch>/after-nyt.json"
```
Expected: `IDENTICAL` and an empty difference list. Repeat for the Once Upon a Chef pair. Any difference is a bug — the parser lookup must be a no-op for non-Outdoor-Eats hosts.

- [ ] **Step 8: Re-run the unit tests**

Run: `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"`
Expected: PASS, 25 passed

- [ ] **Step 9: (OPTIONAL) Commit** — only if the user asks.

---

### Task 6: Template and Base

**Files:**
- Create: `Templates/Camping Recipe.md`
- Create: `Camping.base`

- [ ] **Step 1: Create the template**

`Templates/Camping Recipe.md` — note `date` uses the Obsidian template variable, matching `Templates/Recipe.md`:

```markdown
---
tags: [camping]
title:
author:
servings:
weight-per-serving:
calories-per-serving:
water-needed:
cook-method:
time:
date: "{{date:YYYY-MM-DD dddd}}"
link:
image:
---
Overview

# Title

### 🛒 Ingredients
- 

### 🥣 Steps
1. 
```

`weight-per-serving` is grams (numeric), `water-needed` is millilitres (numeric, `0` for no-cook). `last-cooked:` from `Templates/Recipe.md` is intentionally omitted — it appears in exactly one file vault-wide and is vestigial.

- [ ] **Step 2: Create the Base**

Before writing it, invoke the `obsidian-bases` skill to confirm current `.base` syntax rather than copying blindly. Then create `Camping.base`:

```yaml
filters:
  and:
    - file.ext == "md"
    - file.inFolder("Camping")
properties:
  file.folder:
    displayName: Category
  author:
    displayName: Author
  servings:
    displayName: Servings
  weight-per-serving:
    displayName: Weight / Serving (g)
  calories-per-serving:
    displayName: Cal / Serving
  water-needed:
    displayName: Water (ml)
  cook-method:
    displayName: Method
  time:
    displayName: Time
views:
  - type: cards
    name: Camping
    order:
      - file.name
      - weight-per-serving
      - cook-method
      - time
    sort:
      - property: date
        direction: DESC
    image: note.image
    imageAspectRatio: 1
    imageFit: cover
  - type: table
    name: By Weight
    order:
      - file.name
      - weight-per-serving
      - calories-per-serving
      - water-needed
      - cook-method
      - time
    sort:
      - property: weight-per-serving
        direction: ASC
  - type: table
    name: No-Cook
    filters:
      and:
        - cook-method == "no-cook"
    order:
      - file.name
      - weight-per-serving
      - water-needed
      - time
    sort:
      - property: file.name
        direction: ASC
```

- [ ] **Step 3: Verify LF endings**

```bash
python -c "import sys; [print(p, open(p,'rb').read().count(b'\r')) for p in sys.argv[1:]]" "Templates/Camping Recipe.md" "Camping.base"
```
Expected: `0` for both.

- [ ] **Step 4: (OPTIONAL) Commit** — only if the user asks.

Note: the "No-Cook" view renders empty until a no-cook recipe is imported. Both proof recipes are `one-pot`, so this view is correct-but-unexercised. Expected, not a fault.

---

### Task 7: Import the two proof recipes

**Files:**
- Create: `Camping/Hiker Pasta.md`, `Camping/attachments/Hiker Pasta.png`
- Create: `Camping/Chicken Dijon with Rice.md`, `Camping/attachments/Chicken Dijon with Rice.png`

- [ ] **Step 1: Create the folder and extract both recipes with images**

```bash
mkdir -p "Camping/attachments"
uv run ".claude/skills/download-recipe/scripts/recipe_extract.py" \
  "https://outdooreats.com/recipe/hiker-pasta/" \
  --out "<scratch>/hiker.json" \
  --image "G:/My Drive/Recipes/Camping/attachments/Hiker Pasta.png"
uv run ".claude/skills/download-recipe/scripts/recipe_extract.py" \
  "https://outdooreats.com/recipe/chicken-dijon-with-rice/" \
  --out "<scratch>/dijon.json" \
  --image "G:/My Drive/Recipes/Camping/attachments/Chicken Dijon with Rice.png"
```

Confirm the script reports `format: png` and `800x800` for both. If it reports a different format, rename the file to the true extension and adjust both the `image:` property and the embed.

- [ ] **Step 2: Write `Camping/Hiker Pasta.md`**

Read the JSON and write the note with editorial judgment — the overview is tightened from the site's description, not pasted. Expected values: `servings: 1 serving`, `weight-per-serving: 275`, `water-needed: 400`, `cook-method: one-pot`, `time: 10 minutes`, `author: Corso`, `date: 2026-08-10 Monday` (the date the note is added — recompute if executing on a later day), tags `[camping, one-pot, dairy-free, gluten-free, high-calorie]`. This recipe has no cook's note, so **omit the tip callout entirely**.

- [ ] **Step 3: Write `Camping/Chicken Dijon with Rice.md`**

Expected values: `servings: 2 servings`, `weight-per-serving: 238`, `water-needed: 250`, `cook-method: one-pot`, `time: 15 minutes`, `author: Corso`, tags `[camping, one-pot, gluten-free, nut-free, high-calorie]`. This recipe **does** have a cook's note — put the recovered `cooks_note` in the tip callout:

```markdown
> [!tip] Tip
> You can also cook the sauce separately, before or after the rice, depending on your pot/pan situation.
```

- [ ] **Step 4: Verify both notes**

```bash
python -c "
import sys
for p in sys.argv[1:]:
    b=open(p,'rb').read()
    print(p, 'CR:', b.count(b'\r'), 'bytes:', len(b))
" "Camping/Hiker Pasta.md" "Camping/Chicken Dijon with Rice.md"
ls -la "Camping/attachments/"
```
Expected: `CR: 0` for both notes; two PNG files present.

Then confirm each note's `image:` property names a file that exists, and that the frontmatter carries all four camping fields with numeric values.

- [ ] **Step 5: (OPTIONAL) Commit** — only if the user asks.

---

### Task 8: Documentation

**Files:**
- Modify: `.claude/skills/download-recipe/SKILL.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Correct the paywall claim in `SKILL.md`**

The skill currently asserts as a general truth that paywalls gate the reading experience but not the JSON-LD. Left unqualified it would mislead a future run into assuming content must be recoverable. Add immediately after that paragraph:

```markdown
**This does not hold everywhere.** Outdoor Eats gates server-side (MemberPress):
a locked page contains no ingredients or steps anywhere in the HTML, and its
JSON-LD `Recipe` node is a stub carrying only name and image. About 46% of that
site's 374 recipes are locked. The extractor detects this and exits non-zero
rather than writing an empty note — do not try to work around it.
```

- [ ] **Step 2: Add rule 0 and the folder names in `SKILL.md`**

Add `Camping` and `Sports` to the existing folder list in step 2, then insert above rule 1:

```markdown
0. **CAMPING / BACKPACKING** — from a camping/backpacking site, or explicitly trail,
   camp, or pack food → Camping. This wins over every other rule, **including dish
   type**. "Hiker Pasta" is Camping, not Pasta; "Trail Cioppino" is Camping, not Soups.
   Camping notes use `Templates/Camping Recipe.md`, not the standard recipe template.
```

And after the existing "Grilling is not BBQ" note:

```markdown
**Sports is not Camping.** `Sports/` is sports drinks and exercise nutrition;
`Camping/` is trail and camp food. A high-calorie energy snack from a camping
source goes to Camping; a drink mix or gel for workouts goes to Sports. Source
and intent decide, not the macros.
```

- [ ] **Step 3: Add the Outdoor Eats subsection to `SKILL.md`**

```markdown
### Outdoor Eats / camping recipes

`outdooreats.com` publishes a stub `schema.org/Recipe` node — name and image only.
`recipe-scrapers` reports success and returns zero ingredients, so watch `missing[]`
for a run of `SchemaOrgException` entries. `scripts/site_parsers.py` repairs this from
the page's inline microdata; you do not need to do anything special beyond running the
normal command.

Extras arrive in a `camping` sub-object: `weight_per_serving_g`, `water_needed_ml`,
`cook_method` (always inferred — sanity-check it against the steps), and
`dietary_tags`. A recovered cook's note arrives as `cooks_note` and belongs in the
`> [!tip]` callout. Images are 800×800 PNG, so use `.png` in the attachment name,
the `image:` property, and the embed.

Gated recipes exit with code 2 and write nothing.
```

- [ ] **Step 4: Update `CLAUDE.md`**

Add `Camping` and `Sports` to the folder taxonomy paragraph, and after the `Reference/` section add:

```markdown
## Camping recipes

`Camping/` holds trail and backpacking food and uses **`Templates/Camping Recipe.md`**,
which extends the standard template with `weight-per-serving` (grams, numeric),
`calories-per-serving`, `water-needed` (millilitres, numeric — `0` means no water
needed, blank means unknown), and `cook-method`. `Camping.base` renders these,
sorted by pack weight. The camping folder wins over dish type: "Hiker Pasta" is
Camping, not Pasta. Distinct from `Sports/`, which is sports drinks and exercise
nutrition.
```

- [ ] **Step 5: Verify LF endings on both files**

```bash
python -c "import sys; [print(p, open(p,'rb').read().count(b'\r')) for p in sys.argv[1:]]" "CLAUDE.md" ".claude/skills/download-recipe/SKILL.md"
```
Expected: `0` for both.

- [ ] **Step 6: (OPTIONAL) Commit** — only if the user asks.

---

## Final verification

- [ ] `uv run ".claude/skills/download-recipe/scripts/test_site_parsers.py"` — 25 passed
- [ ] NYT and Serious Eats JSON identical to the pre-change baselines
- [ ] `blta-grain-bowl` exits 2 and writes no file
- [ ] Both notes exist in `Camping/` with 0 CR bytes and all four camping fields populated
- [ ] Both `Camping/attachments/*.png` exist at 800×800
- [ ] **User confirms in Obsidian** that `Camping.base` renders — cards show photos, "By Weight" sorts 238 before 275, "No-Cook" is empty (expected: both recipes are one-pot)
