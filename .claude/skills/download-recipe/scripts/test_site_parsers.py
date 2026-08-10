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


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
