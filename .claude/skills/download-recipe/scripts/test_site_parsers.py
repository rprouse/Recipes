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


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
