# /// script
# requires-python = ">=3.10"
# dependencies = ["beautifulsoup4", "pytest"]
# ///
"""Unit tests for site_parsers, run offline against hand-written fixtures.

Fixtures are minimal HTML reproducing the exact structures found on
outdooreats.com on 2026-08-10 — inline microdata plus the theme's
`.recipe-digits` block. They are hand-written rather than saved pages so the
tests stay small and state precisely which markup each behaviour depends on.

Also covers `recipe_extract.merge_recovered`, the other half of the repair path:
importing `recipe_extract` costs nothing here because it pulls `recipe_scrapers`
in lazily, inside `extract()`.
"""
import recipe_extract
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

# Sun-Dried Tomato Tuna Mix, copied verbatim from the live page: a no-cook recipe
# carries THREE recipeInstructions nodes and the numbered one is in the MIDDLE —
# a "*NO COOK / NO BURNER RECIPE*" banner comes first. It also wraps step 1 over
# two lines, putting an unnumbered fragment BETWEEN steps 1 and 2.
TUNA_STEPS_HTML = """
<div class="recipe-instructions">
  <p itemprop="recipeInstructions">*NO COOK / NO BURNER RECIPE*</p>
  <p itemprop="recipeInstructions">Steps<br />1. Combine all ingredients except crackers/tortillas. <br />Chop or crush nuts/olives as needed<br />2. Mix. Sit 5-10 min<br />3. Dunk with crackers or fill and wrap your tortillas</p>
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

TUNA_INGREDIENTS_HTML = """
<div class="recipe-ingredients-wrap"><h2>Ingredients</h2><ul>
  <li itemprop="recipeIngredient">Tuna, packet - 5 oz / 142 g</li>
  <li itemprop="recipeIngredient">Sun Dried Tomatoes - 1/4 C / 20 g</li>
  <li itemprop="recipeIngredient">Crackers - 2 oz / 56 g</li>
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


def test_unnumbered_fragment_between_steps_joins_the_preceding_step():
    # Step 1 is wrapped over two <br>-separated lines. Only fragments after the
    # LAST numbered step are a cook's note; one sitting between numbered steps is
    # a continuation and belongs on the step above it.
    steps, note = site_parsers._steps_and_note(
        site_parsers._split_on_br(site_parsers._soup(TUNA_STEPS_HTML)
                                 .select('[itemprop="recipeInstructions"]')[1])
    )
    assert len(steps) == 3
    assert steps[0] == (
        "Combine all ingredients except crackers/tortillas. "
        "Chop or crush nuts/olives as needed"
    )
    assert note == ""


# _instructions() picks WHICH recipeInstructions node to read. It shipped untested,
# which is how the three-node no-cook shape below got through returning zero steps.


def test_instructions_reads_the_node_that_carries_the_numbering():
    # The numbered node is second here, so anything that hardcodes an index fails.
    steps, note = site_parsers._instructions(site_parsers._soup(TUNA_STEPS_HTML))
    assert len(steps) == 3, "the *NO COOK* banner paragraph must not shadow the steps"
    assert steps[1] == "Mix. Sit 5-10 min"
    assert "NO COOK" not in " ".join(steps)
    assert "NO COOK" not in note


def test_instructions_excludes_the_signoff_paragraph():
    steps, note = site_parsers._instructions(site_parsers._soup(TUNA_STEPS_HTML))
    assert "EAT & PACK IT OUT" not in " ".join(steps)
    assert "EAT & PACK IT OUT" not in note


def test_instructions_keeps_the_cooks_note_from_the_numbered_node():
    steps, note = site_parsers._instructions(site_parsers._soup(DIJON_STEPS_HTML))
    assert len(steps) == 5
    assert note.startswith("*you can also cook sauce separately")


def test_instructions_on_a_single_numbered_node():
    steps, note = site_parsers._instructions(site_parsers._soup(HIKER_STEPS_HTML))
    assert len(steps) == 7
    assert note == ""


def test_instructions_returns_empty_when_the_markup_has_no_nodes():
    assert site_parsers._instructions(site_parsers._soup("<div><p>nothing</p></div>")) == ([], "")


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


def test_water_none_when_quantity_is_unparseable():
    # A water line with no number means "unknown", which must stay distinct from
    # the 0 returned when there is no water ingredient at all — in the finished
    # note, blank and 0 tell a camper different things about a dry camp.
    assert site_parsers._water_ml(["Water - to taste", "Salt - to taste"]) is None


def test_author_from_microdata_not_the_by_prefix():
    assert site_parsers._author(site_parsers._soup(AUTHOR_HTML)) == "Corso"


def test_author_is_not_the_tester():
    # .recipe-subtitle names the tester (Grammysaurus), who differs from the
    # author (Corso) on chicken-dijon-with-rice. They must not be conflated.
    assert site_parsers._author(site_parsers._soup(AUTHOR_HTML)) != "Grammysaurus"


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


# The no-cook page in full: the site labels it "No Cook" in its own type taxonomy,
# yields 1 serving, and needs no water.
TUNA_TYPES_HTML = """
<div class="fd-recipe-type-cont"><span class="fd-Recipe-Type">High Calorie, Dairy Free, Gluten Free, No Cook, Low Water</span></div>
"""

TUNA_DIGITS_HTML = """
<div class="recipe-digits">
  <div class="recipe-digits-item">
    <div class="digits"><span class="meta-label">Yields</span>
      <span class="meta-servings"><span itemprop="recipeYield">1</span></span></div>
    <div class="text">Servings</div>
  </div>
  <div class="recipe-digits-item">
    <div class="digits text-minutes"><span class="meta-label"></span><span>10</span></div>
    <div class="text">Minutes</div>
  </div>
  <div class="recipe-digits-item">
    <div class="digits text-description"><div itemprop="description"><p>~8.8 oz /<br /> ~250 g</p></div></div>
    <div class="text">Weight per serving</div>
  </div>
</div>
"""

TUNA_FULL_HTML = f"""
<html><body>
  <h1 class="recipe-title">Sun-Dried Tomato Tuna Mix</h1>
  {TUNA_INGREDIENTS_HTML}
  {TUNA_STEPS_HTML}
  {TUNA_DIGITS_HTML}
  {TUNA_TYPES_HTML}
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


def test_cook_method_prefers_the_sites_own_no_cook_tag():
    # The site publishes the answer in its type taxonomy; that beats reading tea
    # leaves in the step text, even when a step happens to mention boiling water.
    assert site_parsers._cook_method(
        ["Boil water for tea alongside"], 0, ["high-calorie", "no-cook", "low-water"]
    ) == "no-cook"


def test_cook_method_without_tags_still_falls_back_to_the_step_text():
    assert site_parsers._cook_method(["Combine and roll"], 0, []) == "no-cook"
    assert site_parsers._cook_method(["Boil. Add rice"], 250, []) == "one-pot"


def test_cook_method_does_not_call_a_missing_step_list_no_cook():
    # An empty step list used to read as no-cook, which is precisely how a broken
    # parse dressed itself up as a valid recipe. A recipe that needs water is not
    # no-cook no matter how little its (absent) steps say about heat.
    assert site_parsers._cook_method([], 400, []) == "one-pot"


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


def test_full_parse_of_a_no_cook_recipe():
    got = site_parsers._parse_outdooreats(TUNA_FULL_HTML, {})
    assert got["title"] == "Sun-Dried Tomato Tuna Mix"
    assert len(got["instructions_list"]) == 3, "three-node markup must still yield steps"
    assert got["instructions_list"][0].endswith("Chop or crush nuts/olives as needed")
    assert got["cooks_note"] == ""
    assert got["camping"]["cook_method"] == "no-cook"
    assert got["camping"]["water_needed_ml"] == 0
    assert got["camping"]["weight_per_serving_g"] == 250
    assert "no-cook" in got["camping"]["dietary_tags"]


def test_single_serving_yield_is_not_pluralised():
    # This site is full of single-serving recipes, and SKILL.md tells the note
    # writer to copy `yields` verbatim — so "1 servings" would land in a note.
    assert site_parsers._parse_outdooreats(TUNA_FULL_HTML, {})["yields"] == "1 serving"
    assert site_parsers._parse_outdooreats(FULL_HTML, {})["yields"] == "2 servings"


def test_full_parse_never_returns_an_image_key():
    # The stub JSON-LD has the right photo; the page markup leads with the site
    # logo (montYbocalogo.png). Returning an image here would overwrite good
    # data with the logo.
    assert "image" not in site_parsers._parse_outdooreats(FULL_HTML, {})


# merge_recovered: what the repair pass tells the caller it did.


def test_merge_fills_only_fields_schema_org_left_empty():
    data = {"title": "From JSON-LD", "ingredients": None}
    missing = [{"field": "ingredients", "error": "SchemaOrgException"}]
    got = recipe_extract.merge_recovered(
        data, {"title": "From page markup", "ingredients": ["Tuna"]}, missing
    )
    assert data["title"] == "From JSON-LD", "schema.org data must never be overwritten"
    assert data["ingredients"] == ["Tuna"]
    assert got == [{"field": "ingredients", "error": "recovered from site parser"}]


def test_merge_records_an_empty_recovered_value_as_a_miss():
    # The C1 silent failure, one layer down: instructions_list came back [], which
    # is falsy, so it was neither merged nor listed and the run reported success
    # with no steps and nothing in missing[] to say so.
    data = {"instructions_list": None}
    got = recipe_extract.merge_recovered(
        data, {"instructions_list": []}, [{"field": "instructions_list", "error": "SchemaOrgException"}]
    )
    assert got == [{"field": "instructions_list", "error": "site parser found nothing"}]


def test_merge_reports_a_miss_even_with_no_prior_missing_entry():
    got = recipe_extract.merge_recovered({}, {"yields": None}, [])
    assert got == [{"field": "yields", "error": "site parser found nothing"}]


def test_merge_stays_quiet_when_schema_org_already_had_the_field():
    data = {"yields": "4 servings"}
    assert recipe_extract.merge_recovered(data, {"yields": None}, []) == []
    assert data["yields"] == "4 servings"


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
