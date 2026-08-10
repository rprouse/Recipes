# Camping recipes from Outdoor Eats — design

**Date:** 2026-08-10
**Status:** approved, ready for implementation

## Problem

The vault should accept recipes from <https://outdooreats.com/> into a new `Camping/`
folder. The existing `download-recipe` skill does not work on this site, and camping
recipes carry planning data (pack weight, water, whether a stove is needed) that
`Templates/Recipe.md` has nowhere to put.

## Findings

Established by probing the live site on 2026-08-10.

### The skill's paywall assumption does not hold here

`SKILL.md` states that sites gate "the rendered reading experience, not the
`schema.org/Recipe` JSON-LD." That is true of NYT Cooking. It is **false** for Outdoor
Eats, which gates server-side via MemberPress: a locked page contains no ingredients or
steps anywhere in the HTML, only a "Join the Outdoor Eats Recipe Club" signup pitch.
Nothing is recoverable from a locked page.

A 24-recipe sample of the 374 in `recipe-sitemap.xml` found **13 free, 11 gated**
(~46% locked). The user does not currently hold a membership.

### Every recipe ships a stub `Recipe` node

Free and gated pages alike publish exactly this much JSON-LD:

```json
{"@type": "Recipe",
 "@id": "https://outdooreats.com/recipe/hiker-pasta/#recipe",
 "name": "Hiker Pasta",
 "author": {"@type": "Person"},
 "image": {"@type": "ImageObject", "url": "...hikerpasta1.png", "width": 800, "height": 800}}
```

No `recipeIngredient`, `recipeInstructions`, `recipeYield`, or `description`. This is a
new failure mode for the vault: enough valid JSON-LD that `recipe-scrapers`' generic
schema.org path reports success, while returning **0 ingredients and 0 steps**. Prior
sites failed loudly (HTTP 403) or completely (no JSON-LD at all). The `missing[]` array
is the only signal — eight `SchemaOrgException` entries.

Recipe content lives in hand-authored WordPress theme markup (`simple-recipe-pro` /
`theme-outdooreats`) under stable class names, not hashed CSS-module names.

### There is no numeric calorie data on this site

What resembles calorie information — `Dairy Free, High Calorie, Gluten Free` — is a
dietary **type taxonomy** (`add-recipe-type-*`), not a number. "High Calorie" is a label
like "Vegan". No page sampled contained a kcal figure.

**Weight per serving is real and reliable**, present in `.recipe-digits` on every free
recipe sampled (e.g. `~10 oz / ~275 g`).

## Decisions

| Question | Decision |
|---|---|
| Calorie field | Keep `calories-per-serving:` in the template, blank when the source has none |
| Membership | Free recipes only for now; structure the code so auth can be added later |
| Extra fields | `water-needed`, `cook-method`; dietary types folded into `tags` |
| Testing location | Not captured |
| Folder rubric | `Camping/` wins over every other rule, including dish type |
| Base | New `Camping.base` |
| Weight and water units | Numeric grams and millilitres, so both sort correctly |
| Integration | Site handler inside `recipe_extract.py`, not a new skill |

## Design

### 1. Extractor — `.claude/skills/download-recipe/scripts/recipe_extract.py`

A hostname-keyed handler consulted immediately after the schema.org pass, at the same
seam where `og_image()` recovery already lives:

```python
SITE_PARSERS = {"outdooreats.com": _parse_outdooreats}
```

Rules the handler obeys:

- **Gate detection runs first.** A page with no `.recipe-ingredients-wrap` is member-
  locked. The script exits non-zero with `recipe is member-gated (Outdoor Eats Recipe
  Club) — no content in page` and writes no JSON. It must never emit a half-empty note.
- **Fill only empty fields.** Anything the schema.org pass already produced is left
  alone.
- **Never touch `image`.** The stub JSON-LD carries the correct recipe photo. An HTML
  scrape does not: the site logo (`montYbocalogo.png`) appears in the markup before the
  recipe image and any loose URL regex grabs it instead. This is the one field the stub
  gets right and a scrape gets wrong.
- **Be honest in `missing[]`** — recovered fields get an entry reading
  `<field>: recovered from site parser`, following the existing `recovered from
  og:image` precedent.
- **No-op for every other host.** An unknown hostname changes nothing.

Selectors, all confirmed against live HTML:

| Field | Source |
|---|---|
| ingredients | `.recipe-ingredients-wrap` list items |
| steps | `.recipe-instructions-wrap` |
| yields, time, weight | `.recipe-digits-item` |
| dietary types | `.fd-recipe-type-cont` |
| author | `.recipe-author` |

Parsing hazards found in the two test recipes:

- **Steps arrive as one blob**, `<br>`-separated rather than as list items, and on
  Chicken Dijon the `<h2>` text bleeds in: `Steps 1. TURN ON BURNER: HIGH HEAT 2. Add
  chicken...`. Split on the leading `N.` numbering, strip the numbering, and discard a
  leading `Steps` fragment. Drop the trailing `EAT & PACK IT OUT` sign-off.
- **Author strings are unspaced**: `.recipe-author` is `byCorso` → `Corso`. Strip the
  `by` prefix and normalize whitespace.
- **Author and tester are different people.** `.recipe-subtitle` on Chicken Dijon is
  `Tested byGrammysaurus` while the author is `Corso`. They coincide on Hiker Pasta and
  must not be treated as interchangeable. Only `.recipe-author` feeds `author:`.
- **Weight carries a `~` estimate marker**: `~8.4 oz / ~238 g` → `238`.
- **Water can be a range**: Hiker Pasta lists `Water - 8-12 oz / 400 ml`. Take the
  millilitre figure the site gives; where only a range is available, take the **upper
  bound** — under-packing water is the failure that matters — and note it in the report.

Camping extras are returned under a `camping` sub-object so non-camping consumers never
see them:

```json
"camping": {"weight_per_serving_g": 238, "water_needed_ml": 250,
            "cook_method": "one-pot", "dietary_types": ["High Calorie", "Gluten Free", "Nut Free"]}
```

`cook_method` is inferred from step text and always reported as inferred, so the user can
override it. The full rule, covering all four enum values:

| Condition | Value |
|---|---|
| No heating step at all | `no-cook` |
| Steps rehydrate in a bag/pouch, no pot | `freezer-bag` |
| Water boiled, then ingredients added off heat or steeped | `boil-only` |
| Everything cooked together in one vessel | `one-pot` |

Where the steps do not clearly match any branch, emit `one-pot` (the commonest case on
this site) and say so in the import report rather than guessing silently.

`beautifulsoup4` gets an explicit PEP 723 entry. It is already present transitively via
`recipe-scrapers` (confirmed 4.15.0), so this adds no resolution cost.

An `auth` hook stays stubbed and unused: a `cookie=` parameter threaded through
`fetch()`, so membership support is later a small change rather than a rewrite.

### 2. Template — `Templates/Camping Recipe.md` (new)

```markdown
---
tags: [camping, <cook-method>, <dietary descriptors>]
title: <Recipe Name>
author: <author>
servings: <e.g. 2 servings>
weight-per-serving: <grams, numeric, e.g. 238>
calories-per-serving: <blank when the source gives none>
water-needed: <millilitres, numeric, e.g. 250 — 0 for no-cook>
cook-method: <no-cook | boil-only | one-pot | freezer-bag>
time: <e.g. 15 minutes>
date: <YYYY-MM-DD dddd>
link: <source URL>
image: "[[attachments/<Recipe Name>.png]]"
---
![[attachments/<Recipe Name>.png]]

# <Recipe Name>

<overview paragraph>

### 🛒 Ingredients
- ...

### 🥣 Steps
1. ...

> [!tip] Tip
> <optional>
```

Field order extends the vault's established sequence, inserting the camping fields after
`servings` because three of the four are serving-scoped. The body is unchanged from
`Templates/Recipe.md`: a camping note is a recipe note with four extra properties.

Notes:

- `weight-per-serving` is **numeric grams** and `water-needed` is **numeric
  millilitres**, so `Camping.base` sorts both natively. Human strings like
  `10 oz / 275 g` would sort lexically and place `10 oz` before `8 oz`.
- `water-needed: 0` for no-cook recipes, never blank. Blank means unknown; `0` means
  genuinely no water required. The distinction matters when planning a dry camp, and
  numeric units express it more cleanly than the string `none` would have — `0` also
  sorts to the top, which is the right place for the meals that need no water.
- `cook-method` is both a field and a tag — the field drives the Base column, the tag
  makes it searchable. This mirrors how `tags` already duplicates the folder name.
- `last-cooked:` from `Templates/Recipe.md` is **not** carried over. It appears in
  exactly one file in the vault (that template) and is vestigial.
- Images from this site are **800×800 PNG**, so the attachment, the `image:` property,
  and the embed all use `.png`.

### 3. Folder rubric

New rule 0 in the skill's step 2, above all existing rules:

> 0. **CAMPING / BACKPACKING** — sourced from a camping/backpacking site, or explicitly
>    trail, camp, or pack food → `Camping`. This wins over every other rule, **including
>    dish type**. "Hiker Pasta" is Camping, not Pasta; "Trail Cioppino" is Camping, not
>    Soups.

This inverts the vault's "dish type wins" precedence for exactly one case, so it is
stated first rather than buried.

`Sports/` also gets added to both folder lists — it exists in the vault but appears in
neither `CLAUDE.md` nor `SKILL.md`. Its boundary against Camping needs stating, because
Outdoor Eats publishes drink mixes and energy snacks that could read as either:

> `Sports/` is sports drinks and exercise nutrition. `Camping/` is trail and camp food.
> A high-calorie energy snack from a camping source goes to Camping; a drink mix or gel
> for workouts goes to Sports. Source and intent decide, not the macros.

### 4. `Camping.base` (new)

Follows the conventions of the two existing Bases — `properties:` with `displayName`,
a cards view plus table views.

```yaml
filters:
  and:
    - file.ext == "md"
    - file.inFolder("Camping")
properties:
  weight-per-serving: {displayName: Weight / Serving (g)}
  calories-per-serving: {displayName: Cal / Serving}
  water-needed: {displayName: Water (ml)}
  cook-method: {displayName: Method}
views:
  - cards, newest first — mirrors All Recipes
  - table: Name | Weight | Cal | Water | Method | Time, sorted by weight ASC
  - table "No-Cook": filtered to cook-method == "no-cook"
```

The third view earns its place: no-cook meals are what you reach for without fuel, and
that is a question asked while packing.

No changes to `All Recipes.base` or `Make Again.base`. Their filters exclude only
`Incoming`, `Templates`, and `Reference`, so `Camping/` notes appear in them
automatically.

### 5. Documentation

- **`SKILL.md`** — add `Camping` and `Sports` to the folder list; add rule 0 and the
  Sports/Camping boundary; add an "Outdoor Eats / camping recipes" subsection covering
  the member gate, the `camping` JSON sub-object, and the camping template. Amend the
  paywall paragraph, which currently asserts as a general truth that JSON-LD survives
  paywalls — true for NYT, false here, and left unqualified it would mislead a future
  run into assuming content must be recoverable.
- **`CLAUDE.md`** — add `Camping` and `Sports` to the folder taxonomy, note the camping
  template alongside the existing `Reference/` guidance, and record that this site's
  images are 800×800 PNG.

## Testing

Regression matters more than the new feature, since this touches the extractor every
other site depends on.

1. **Both test recipes import end-to-end and stay in the vault:**

   | | Hiker Pasta | Chicken Dijon with Rice |
   |---|---|---|
   | servings | 1 | 2 |
   | weight-per-serving | 275 | 238 |
   | time | 10 minutes | 15 minutes |
   | water-needed | 400 | 250 |
   | cook-method | one-pot | one-pot |
   | tags | dairy-free, gluten-free, high-calorie | gluten-free, nut-free, high-calorie |

   Both land in `Camping/` with `attachments/<Name>.png` at 800×800.
2. **Gate path:** `https://outdooreats.com/recipe/blta-grain-bowl/` exits non-zero with
   a clear message and writes **no** file. Verified by asserting the note is absent.
3. **Regression:** run the extractor against one NYT URL and one Serious Eats URL and
   diff the JSON against a pre-change run. The `SITE_PARSERS` lookup must be a no-op for
   every other host — the likeliest silent breakage.
4. **LF check:** Python `\r` byte-count on both new notes, expecting 0. Not
   `grep -c $'\r'`, which false-positives on these UTF-8 notes.
5. **Base rendering:** cannot be verified headlessly. The user confirms in Obsidian.

Known gap: both test recipes are `one-pot`, so the "No-Cook" view will render empty
until a no-cook recipe is imported. That is correct behaviour, not a fault — but it
means the view's filter is unexercised by this round of testing.

## Out of scope

- **Bulk-importing the remaining ~200 free recipes.** A separate decision about how much
  of another author's catalogue to copy into the vault, to be made after seeing the two
  proof notes.
- **Membership/authenticated fetch** for the ~46% gated recipes. The `cookie=` hook is
  stubbed; nothing reads it.
- Any change to `All Recipes.base` or `Make Again.base`.
- Committing. The user backs up the vault via obsidian-git.
