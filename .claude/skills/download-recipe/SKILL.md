---
name: download-recipe
description: >-
  Download a recipe from ANY cooking website — NYT Cooking, Serious Eats, Once Upon
  a Chef, AllRecipes, Bon Appétit, Food Network, Smitten Kitchen, food blogs — and
  save it into this Obsidian recipe vault as a formatted note, lead image and all.
  Use this whenever the user gives a recipe URL and wants it saved, imported,
  clipped, grabbed, or added to the vault — "save this recipe", "add this to my
  recipes", "import this recipe", "clip this", "grab this recipe". The user supplies
  the URL; this skill does NOT invent a recipe.
---

# Download a web recipe into the vault

Turns a recipe URL into a finished vault note: correct folder, frontmatter, an
overview paragraph, ingredients, steps, an optional cook's tip, and the lead photo
embedded at the top (downloaded to an `attachments/` subfolder beside the note).

**One skill for every site, including NYT Cooking.** Essentially all recipe sites
publish `schema.org/Recipe` JSON-LD for SEO, so a single extractor handles them.
Paywalls generally gate the *rendered reading experience*, not that structured data
— NYT included, so no login is needed to import a single recipe.

The extractor produces data. **You** interpret it and write the note, so tags, the
overview paragraph, and the `time:` phrasing match the vault's style.

## 1. Extract the recipe

One script, run through `uv` — the PEP 723 header declares `recipe-scrapers`, so uv
resolves it on first run. **No manual `pip install`.**

```bash
uv run .claude/skills/download-recipe/scripts/recipe_extract.py "<recipe url>" \
    --out "<scratch>/recipe.json"
```

Read the JSON, then decide the folder (step 2) so you know where the image goes.
Once you know, re-run with `--image` pointing at the final path — or download it
separately in step 3.

The JSON carries: `title`, `author`, `yields`, `total_time` / `prep_time` /
`cook_time` (raw minutes), `time_human`, `description`, `category`, `cuisine`,
`keywords[]`, `dietary_restrictions`, `ingredients[]`, `instructions_list[]`,
`image`, `site_name`, `canonical_url`, and `missing[]`.

**Reading `missing[]`:** it names each field that could not be extracted, with the
exception type. Most entries are benign — `cuisine` is absent from NYT recipes,
`keywords` from Serious Eats. Only worry when something you need is listed. An entry
reading `image: recovered from og:image` means schema.org had no image and it came
from the `og:image` meta tag instead; that is a success, not a failure.

**Other flags:** `--save-html <path>` keeps the page for inspection (see "Ingredient
groups" below). `--best-image` selects by raw pixel count — **usually wrong here**:
on NYT it returns the 1800×1800 square crop instead of the 1600×900 landscape hero
that all existing notes use. Leave it off unless a site's default image is poor.

### If extraction fails

- **`HTTP Error 403` after retries.** Dotdash Meredith sites (Serious Eats, Simply
  Recipes, AllRecipes, Food & Wine) hand out **intermittent** 403s to automated
  clients. It is rate-limiting, not fingerprinting — curl and Python both see a
  random mix of 200 and 403 on the same URL seconds apart, so switching tools does
  not help. The script already retries 5 times with backoff; if it still fails,
  wait a minute and re-run the identical command.
- **No JSON-LD at all** (rare — some personal blogs). Fall back to the `defuddle`
  skill (`defuddle parse "<url>" --md`) and read the recipe out of the markdown by
  hand, or use `WebFetch`. Then continue from step 2 as normal.
- Anything else: stop and report it rather than guessing at the recipe.

## 2. Pick the destination folder

Existing folders: **Baking, BBQ, Beef, Breakfast, Chicken, Desserts, Drinks,
Mexican, Noodles, Pasta, Pizza, Pork, Salads, Sandwiches, Seafood, Sides, Snacks,
Soups, Sous Vide, Vegetarian**. Use `Incoming` only as a true last resort. Apply in
priority order:

1. PASTA dish (spaghetti, fettuccine, gnocchi, macaroni, orzo, lasagna) → Pasta.
   ASIAN NOODLE dish (ramen, soba, udon, lo mein, rice noodles, pho) → Noodles.
2. SOUP or STEW (brothy, soup, stew, chili, chowder) → Soups.
3. SALAD → Salads.
4. SANDWICH (sub, hoagie, banh mi, panini, melt, wrap, burger, BLT) → Sandwiches.
5. PIZZA → Pizza. MEXICAN (tacos, enchiladas, quesadillas, mole) → Mexican.
6. BREAKFAST (waffles, pancakes, eggs, granola, oatmeal, breakfast bars) → Breakfast.
7. Bread/cracker/cornbread/biscuit/muffin → Baking. Sweet dessert → Desserts.
   Snack bar (energy/granola bars not for breakfast) → Snacks. Beverage → Drinks.
8. Protein-forward main by primary protein: Beef, Chicken (incl. turkey/poultry),
   Pork (bacon, sausage, ham), Seafood (fish, shrimp, salmon, scallops).
9. Meatless main with no better home → Vegetarian. Condiment/ferment/dressing/
   slaw/pickle/sauce/spice-paste → Sides.
10. BBQ or Sous Vide ONLY if explicitly that method.

When a dish is both a pasta/noodle/soup/salad/sandwich AND has a protein (e.g.
"Shrimp Piccata Spaghetti", "Spicy Pork Noodle Soup", "Steak Banh Mi"), DISH TYPE
wins over protein.

**Grilling is not BBQ.** `BBQ/` is for actual barbecue and smoking (ribs, pulled
pork, smoked wings). Grilled chicken and steak mains go to their protein folder.

Mention any close call so the user can move it.

## 3. Download the lead image

Save it beside the note, named exactly after the note:

```bash
uv run .claude/skills/download-recipe/scripts/recipe_extract.py "<recipe url>" \
    --out "<scratch>/recipe.json" \
    --image "G:/My Drive/Recipes/<Folder>/attachments/<Recipe Name>.jpg"
```

The script verifies the bytes are a real image and reports format and dimensions —
check them. If `format` is not `jpeg`, rename the file to the true extension and
adjust both the `image:` property and the embed. If there is no usable image, skip
the embed and the `image:` property rather than pointing at a broken link.

## 4. Write the note

`<Folder>/<Recipe Name>.md`. Filename: keep the natural title (spaces are fine);
strip only filesystem-illegal characters (`\ / : * ? " < > |`). If a *different*
recipe already owns the filename, disambiguate with the author: `<Name> - <Author>.md`.

```markdown
---
tags: [<folder>, <descriptors>]
title: <Recipe Name>
author: <author or source site>
servings: <e.g. 6 servings>
time: <human text>
date: <today as YYYY-MM-DD dddd>
link: <recipe URL>
image: "[[attachments/<Recipe Name>.jpg]]"
---

![[attachments/<Recipe Name>.jpg]]

# <Recipe Name>

<overview paragraph>

### 🛒 Ingredients
- <each ingredient, verbatim>

### 🥣 Steps
1. <each step, in order>

> [!tip] Tip
> <only if the page offers real guidance; DROP the callout entirely otherwise>
```

Conventions that matter:

- **`image:` is required when an image exists.** It is load-bearing, not decorative:
  `All Recipes.base` and `Make Again.base` both render their card views with
  `image: note.image`, so a note without it shows a blank card. Quote the value:
  `image: "[[attachments/<Name>.jpg]]"`. The embed on the line below is separate —
  the note needs **both**.
- **`tags` inline**, lowercase: `tags: [chicken, quick, weeknight]`. First tag mirrors
  the folder. Add genuinely useful descriptors — draw them from `keywords`, `cuisine`
  (e.g. `cuisine: Indian` → `indian`), and `dietary_restrictions` (which is what puts
  `vegan`/`vegetarian` on a note). Seasons and `make-ahead`/`party` are established in
  this vault and fine to keep. Obsidian's property editor rewrites
  individual notes to a block list when the user edits properties there; that is
  harmless, don't convert notes back.
- **`date` is today**, `YYYY-MM-DD dddd` — the date added, not the publish date.
- **`time`** is human text and yours to judge. The vault uses both `4 hours 15
  minutes` and `95 minutes`, which is why the JSON gives you `total_time` and
  `time_human`. Prefer `time_human` for long recipes; a bare minute count reads
  better under an hour. For a multi-stage recipe an honest span beats a misleading
  total: `15 min prep + 24 hr sous vide + 2 hr finish`. Leave blank if the page
  gives nothing. Note `total_time` is not always `prep + cook`.
- **`servings`** — `yields` verbatim (e.g. `6 servings`).
- Keep ingredient and step text faithful. Trim whitespace; don't paraphrase
  quantities or temperatures.
- **Overview paragraph**: tighten the extracted `description` into something that
  reads well, in the author's spirit. Don't pad it.
- **Tip callout**: the extractor does not pull tips — schema.org has no field for
  them. If the page buries useful guidance in prose (a doneness table, "buy the
  fatty cut"), fold it into the callout. Otherwise omit the callout entirely.

### Ingredient groups

`schema.org`'s `recipeIngredient` is a **flat array by spec**, so a recipe's
ingredient *groups* are lost in extraction. Usually harmless — but when the flat
list implies two components, the result is genuinely confusing. A real example:
a marinade listing `1 ½ cups plain yogurt` and a sauce listing `1 cup plain yogurt`
arrive as two adjacent, unexplained yogurt entries.

When the list looks like it spans components (duplicate ingredients, trailing
`Salt` after a garnish, steps that say "make the sauce"), recover the grouping and
add subheadings, matching the convention in `Pasta/Caesared Spaghetti.md`:

```markdown
### 🛒 Ingredients

**For the Chicken:**
- ...

**For the Tahini-Yogurt Sauce:**
- ...
```

To find the real grouping, re-run with `--save-html` and look for the group
headings in the page. On NYT they are `h3` nodes inside the embedded
`"ingredients":{"doc":{...}}` app-data blob, which is more stable than the
auto-generated CSS class names.

## 5. Verify and report

This vault pins LF (`core.autocrlf false`). The Write tool preserves `\n` on this
machine, but verify with a **Python byte-count**:

```bash
python -c "import sys; print(open(sys.argv[1],'rb').read().count(b'\r'))" "<Folder>/<Name>.md"   # expect 0
```

Do **not** use `grep -c $'\r'` — on these UTF-8 notes (emoji, fractions, accents) it
false-positives and returns the line count even when the file is pure LF. If nonzero:
`python -c "import sys; p=sys.argv[1]; open(p,'wb').write(open(p,'rb').read().replace(b'\r\n',b'\n'))" "<path>"`

Also confirm the image file exists at the path the `image:` property names, and that
its dimensions look like a hero image rather than a thumbnail.

Then report: note path, image path, folder chosen (and why, if it was a close call),
and any judgment calls — how you phrased `time`, what went in the tip, whether you
split ingredient groups, and anything the source didn't provide.

**Don't commit.** The user backs up the vault via the obsidian-git keybindings; files
sync to Google Drive on their own.

## Notes

- Run Python with `python`, never `python3` — on this Windows machine `python3` is the
  Microsoft Store stub and aborts. `uv run` handles the script's own interpreter.
- Recipe text is UTF-8 (`½`, `é`, curly quotes). The Windows console may render these
  as `�` in a `print` preview while the file bytes are perfectly correct — **trust the
  file, not the console**.
- Never pipe a vault-wide file list through `xargs`: note filenames contain spaces and
  `xargs` word-splits them, silently producing wrong counts. Use `grep -rl … -Z | xargs -0`,
  or Python `os.walk`.
