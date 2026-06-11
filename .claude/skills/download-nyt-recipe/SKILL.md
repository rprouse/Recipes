---
name: download-nyt-recipe
description: >-
  Download recipes from NYT Cooking (cooking.nytimes.com) and save them into this
  Obsidian recipe vault as formatted notes, images and all. Use this whenever the
  user gives a NYT Cooking recipe URL and wants it saved, imported, clipped, or
  added to the vault — or says "grab this recipe", "save this NYT recipe", "add
  this to my recipes", "import this from NYT Cooking". ALSO use it to bulk-import
  the user's whole NYT recipe box / saved recipes (see "Bulk import" below). For a
  single recipe the user supplies the URL; this skill does NOT invent a recipe.
  Fetches the page's structured recipe data, downloads the lead image to an
  attachments folder, and writes the note using Templates/Recipe.md.
---

# Download NYT Cooking recipes into the vault

Produces finished notes in this vault — correct folder, frontmatter from
`Templates/Recipe.md`, ingredients, steps, the cook's tip, and the lead photo
embedded at top (downloaded to an `attachments/` subfolder beside the note).

Two modes:
- **Single recipe** from a URL the user gives → needs no login, just `curl`.
- **Bulk import** of the whole recipe box → needs the user's login once, only to
  list what's saved. See [Bulk import](#bulk-import-whole-recipe-box).

## The key fact: an individual recipe needs no login

NYT Cooking gates the *rendered reading experience*, but ships the complete
**`schema.org/Recipe` JSON-LD** (name, author, times, yield, ingredients, steps,
image) in the raw server HTML for SEO — and the cook's **tip** too (in a separate
embedded blob). So a plain `curl` of any recipe URL gets everything; you do **not**
need the Playwright browser or a subscription to read a single recipe. Images live
on a public CDN (`static01.nyt.com`) and download with a normal request.

The browser is only needed to **enumerate the recipe box** (the saved-recipes list
is behind auth) — see Bulk import.

## Single recipe — workflow

You can do this inline (below) or, for convenience, run the bundled script:
`python .claude/skills/download-nyt-recipe/scripts/nyt_fetch.py <one-line-manifest>`
then classify + `nyt_write.py`. Inline is usually faster for one recipe:

### 1. Fetch the page

```bash
curl -sSL -A "Mozilla/5.0" "<recipe url>" -o /tmp/recipe.html
```

### 2. Parse the recipe data

Extract the `<script type="application/ld+json">` whose `@type` is `Recipe`
(handle a top-level array or an `@graph` wrapper) and read: `name`, `author.name`,
`recipeYield`, `totalTime`, `description`, `recipeCategory`, `keywords`,
`suitableForDiet`, `recipeIngredient[]`, `recipeInstructions[]`, `image[]`.

**Edge cases that bite at scale** (the bundled `nyt_fetch.py` handles all of these):
- The `<script>` tag carries extra attributes — it's actually `<script
  type="application/ld+json" data-next-head="">`, not a bare `<script
  type="application/ld+json">`. Match it loosely
  (`<script[^>]*type="application/ld\+json"[^>]*>`) or the regex finds nothing.
- `recipeInstructions` mixes plain `HowToStep` (`.text`) with `HowToSection`
  wrappers whose `.itemListElement` holds the step — flatten recursively.
- `keywords` and `suitableForDiet` may be a **string OR a list** — coerce before
  `.split`/`.lower`.
- `recipeYield` may be a string or a list.
- Older recipes have **no `totalTime`** — leave `time:` blank, that's fine.
- `totalTime` is ISO-8601: `PT0H30M` → "30 minutes", `PT1H35M` → "1 hour 35 minutes".
- The JSON-LD `image` is sometimes **`null`** — fall back to the `og:image` meta tag
  (see step 5). `nyt_fetch.fallback_image()` does this.
- The note text is UTF-8 (fractions ½ ¼, curly apostrophes). On Windows the console
  renders these as `�` when you `print`, but the bytes are fine — **write the note
  from Python with `encoding="utf-8"`** rather than echoing through the shell, and
  don't trust a `print`/`repr` preview to judge corruption.

### 3. Get the cook's tip (NOT in the JSON-LD)

The tip lives in an embedded app-data blob, not the JSON-LD:
`"tips":[{"__typename":"ScoopRecipeTip","details":{"doc":{...}}}]`. Find `"tips":`
in the HTML, JSON-decode the array that follows (Python: `JSONDecoder().raw_decode`
at that offset), and collect the nested `"text"` fields. Skip the callout if absent.
(Don't grep `body` text for "Tip" — that catches reviews quoting the tip.)

### 4. Pick the destination folder

Match to a top-level folder by main ingredient / dish type / cuisine — see the
[folder rubric](#folder-rubric). Mention any close call so the user can move it.

### 5. Download the lead image

From the `image[]` crops, prefer the **largest landscape** — usually the
`...videoSixteenByNineJumbo1600.jpg` (1600×900); else the widest `url`/`contentUrl`.
A User-Agent is required or the CDN refuses:

```bash
cd "<vault>/<Folder>" && mkdir -p attachments && \
curl -sSL -A "Mozilla/5.0" -o "attachments/<Recipe Name>.jpg" "<image url>"
```

If the JSON-LD `image` is `null` (it happens — e.g. `1024405-saag-shrimp`), recover
the lead photo from the **`og:image` meta tag**, then upgrade the crop: the og URL is
the `...-facebookJumbo-v2.jpg` (1200×630) crop of the same asset; the same directory
also holds `...-videoSixteenByNineJumbo1600-v2.jpg` (1600×900). Confirm the bigger
crop exists by grepping the HTML for it under the same asset path rather than guessing
the filename. `nyt_fetch.fallback_image()` implements exactly this.

Verify it's a real image (`file` reports JPEG/PNG, non-trivial size). Skip the embed
if there's no image.

### 6. Write the note

`<Folder>/<Recipe Name>.md`, image embedded at top, following `Templates/Recipe.md`:

```markdown
---
tags: [<folder + useful descriptors like quick, weeknight, vegetarian>]
title: <name>
author: <author.name>
servings: <recipeYield>
time: <totalTime as human text, e.g. 35 minutes>
date: <today as YYYY-MM-DD dddd, e.g. 2026-05-28 Thursday>
link: <recipe URL>
---
![[attachments/<Recipe Name>.jpg]]

# <name>

<description>

### 🛒 Ingredients
- <each recipeIngredient, trimmed>

### 🥣 Steps
1. <each step, in order>

> [!tip] Tip
> <the cook's tip, if any>
```

- `date` is **today** in `YYYY-MM-DD dddd` format, not the recipe's publish date.
- Keep ingredient/step text verbatim; just trim whitespace and obvious artifacts.
- `![[attachments/<Name>.jpg]]` is an Obsidian wikilink embed (see `obsidian-markdown`).
- **Filename collisions:** if `<Folder>/<Name>.md` already exists but is a *different*
  recipe (its NYT id isn't in the file), don't overwrite or skip — disambiguate by
  appending the author, then the id: `<Name> - <Author>.md`, then `<Name> (<id>).md`.
  Two different "Fried Rice" or "Kimchi" recipes are common.

### 7. Report back

Note path, image path, folder chosen (and why if close), any judgment calls.

## Folder rubric

Existing folders: **Baking, BBQ, Beef, Chicken, Mexican, Noodles, Pasta, Pizza,
Sides, Sous Vide, Vegetarian**. Folders added during the bulk import: **Breakfast,
Seafood, Pork, Soups, Salads, Desserts, Snacks, Drinks**. Use `Incoming` only as a
true last resort. Apply in priority order:

1. PASTA dish (spaghetti, fettuccine, gnocchi, macaroni, orzo, lasagna) → Pasta.
   ASIAN NOODLE dish (ramen, soba, udon, lo mein, rice noodles, pho) → Noodles.
2. SOUP or STEW (brothy, soup, stew, chili, chowder) → Soups.
3. SALAD → Salads.
4. PIZZA → Pizza. MEXICAN (tacos, enchiladas, quesadillas, mole) → Mexican.
5. BREAKFAST (waffles, pancakes, eggs, granola, oatmeal, breakfast bars) → Breakfast.
6. Bread/cracker/cornbread/biscuit/muffin → Baking. Sweet dessert → Desserts.
   Snack bar (energy/granola bars not for breakfast) → Snacks. Beverage → Drinks.
7. Protein-forward main by primary protein: Beef, Chicken (incl. turkey/poultry),
   Pork (bacon, sausage, ham), Seafood (fish, shrimp, salmon, scallops).
8. Meatless main with no better home → Vegetarian. Condiment/ferment/dressing/
   slaw/pickle/sauce/spice-paste → Sides.
9. BBQ or Sous Vide ONLY if explicitly that method.

When a dish is both a pasta/noodle/soup/salad AND has a protein (e.g. "Shrimp Piccata
Spaghetti", "Spicy Pork Noodle Soup"), DISH TYPE wins over protein.

## Bulk import (whole recipe box)

To import many/all of the user's saved recipes. Architecture: **enumerate via the
recipe-box API (browser, once) → fetch+parse each via curl (script, no browser) →
classify folders (model judgment) → write notes + images (script).** Each stage is
resumable.

### A. Enumerate the recipe box (needs login)

The saved list is client-side rendered, but the page calls a clean JSON API. Get the
user logged in (see [browser setup](#browser-setup-for-bulk-listing)), then from the
browser context fetch every page (shares the login cookies):

```js
// browser_evaluate — find USER_ID first via /api/v5/users/me or the network log
async () => {
  const base = 'https://cooking.nytimes.com/api/v2/users/<USER_ID>/search/recipe_box_search?q=&per_page=48&page=';
  const seen = new Set(), lines = [];
  for (let p = 1; p <= 40; p++) {
    const r = await fetch(base + p, { credentials: 'include' });
    if (r.status !== 200) break;
    const arr = (await r.json()).collectables || [];
    if (!arr.length) break;
    for (const c of arr) if (!seen.has(c.id)) { seen.add(c.id); lines.push(c.id + '|' + c.url); }
  }
  return `TOTAL=${seen.size}\n` + lines.join('\n');
}
```

The result (`id|url` per line) may overflow the tool output to a file — that's fine,
read it and build `manifest.json` = `[{"id","url"}]`. (`collectables[]` also has
`name`, `byline`, `yield`, etc. if you want richer manifest entries.)

### B. Fetch + parse all (no browser)

```bash
python .claude/skills/download-nyt-recipe/scripts/nyt_fetch.py <work>/manifest.json
```
Skips recipes already in the vault and already cached; writes `cache/<id>.json` and
`classify_input.json`. Polite 1s/recipe by default (`--sleep`).

### C. Classify folders (the only model step)

Split `classify_input.json` into batches (~100) and fan out **Sonnet** sub-agents in
parallel (one per batch), each writing `out_N.json`. **Use Sonnet, not Haiku** — a
subagent inherits the full MCP tool catalog, which overflows Haiku's context
("Prompt is too long"). Give each agent the [folder rubric](#folder-rubric) and have
it return `{"assignments": {"<id>": "<Folder>"}, "new_folders_used": [...]}`. Merge
the batches and **validate**: every input id present exactly once, every folder in
the allowed set. Don't trust the agents' prose counts — verify the files. Write the
merged result to `<work>/folders.json`.

### D. Write notes + images

```bash
python .claude/skills/download-nyt-recipe/scripts/nyt_write.py
```
Downloads images and writes notes. Collision-safe and resumable: re-run any time; it
skips a recipe only when its OWN note already exists, and disambiguates same-title
recipes (see step 6). After it finishes, verify nothing is shadowed — for each id,
confirm a note exists whose body contains that id.

### E. Report

Folder distribution, any new folders created, total notes/images, and any
disambiguated filenames — for the user to review before committing.

## Browser setup (for bulk listing)

Only needed for stage A. The Playwright MCP must drive an **installed** browser in
**headed** mode so the user can log in. This vault uses Firefox. If a `browser_*`
tool errors with `Chromium distribution 'chrome' is not found` or
`Browser "firefox" is not installed`:

1. Add `"--browser", "firefox"` to the args in both Playwright MCP configs:
   - `~/.claude/plugins/cache/claude-plugins-official/playwright/unknown/.mcp.json`
   - `~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/playwright/.mcp.json`
2. `npx @playwright/mcp@latest install-browser firefox`
3. Ask the user to reconnect via `/mcp` (config is read only at server startup).

Navigate to `https://cooking.nytimes.com/recipe-box`; if it shows a Subscribe wall,
ask the user to log in in the Firefox window. The profile is persistent, so login
sticks across runs (an occasional transient redirect to `/auth/login` clears on retry).

## Notes on robustness

- **Run the scripts with `python`, not `python3`.** On this Windows machine `python3`
  resolves to the Microsoft Store stub (`…\WindowsApps\python3`) and aborts with "Python
  was not found"; `python` is the real interpreter (3.14). All commands here use `python`.
- No JSON-LD `Recipe` in the HTML usually means a transient/incomplete fetch — retry.
- A full `browser_snapshot` on NYT can exceed the tool output limit; prefer targeted
  `browser_evaluate` / `curl` + parse over big snapshots.
- Filenames: keep the natural title (spaces are fine here); strip only the characters
  illegal on the filesystem (`\ / : * ? " < > |`).
- Bulk image pulls add up (hundreds of MB) and this vault syncs to Google Drive —
  worth flagging to the user before a large run.
```
