---
name: download-nyt-recipe
description: >-
  Download a recipe from NYT Cooking (cooking.nytimes.com) and save it into this
  Obsidian recipe vault as a formatted note, image and all. Use this whenever the
  user gives a NYT Cooking recipe URL and wants it saved, imported, clipped, or
  added to the vault — or says things like "grab this recipe", "save this NYT
  recipe", "add this to my recipes", or "import this from NYT Cooking". The user
  supplies the recipe URL; this skill does NOT pick a recipe for them. Drives a
  logged-in Firefox via the Playwright MCP, reads the page's structured recipe
  data, downloads the lead image to an attachments folder, and writes the note
  using Templates/Recipe.md.
---

# Download an NYT Cooking recipe into the vault

This skill takes a **single NYT Cooking recipe URL** and produces a finished note
in this vault: correct folder, frontmatter from `Templates/Recipe.md`, ingredients,
steps, any cook's tip, and the lead photo embedded at the top (downloaded to an
`attachments/` subfolder beside the note).

The user provides the URL. Do not browse the recipe box or guess a recipe — if the
user hasn't given a URL, ask for one.

## Why it works the way it does

NYT Cooking is subscriber-only and renders most content with JavaScript, so a plain
HTTP fetch returns a paywall stub. The reliable path is a **logged-in browser** plus
the page's embedded **`schema.org/Recipe` JSON-LD** — a clean, structured blob with
the name, author, times, yield, ingredients, and steps. Parsing that is far more
robust than scraping rendered HTML. The images, by contrast, live on a public CDN
(`static01.nyt.com`) and download fine with a normal request.

## Prerequisites (one-time, usually already done)

The Playwright MCP must drive a **browser that is actually installed**, in **headed**
mode so the user can log in. This vault is configured to use Firefox. If a
`browser_*` tool fails with `Chromium distribution 'chrome' is not found` or
`Browser "firefox" is not installed`, fix it before continuing:

1. Edit the Playwright MCP config(s) so the args include `"--browser", "firefox"`:
   - `~/.claude/plugins/cache/claude-plugins-official/playwright/unknown/.mcp.json`
   - `~/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/playwright/.mcp.json`
2. Install the matching browser build: `npx @playwright/mcp@latest install-browser firefox`
3. Ask the user to reconnect the server (`/mcp` → reconnect **playwright**) — config
   is only read at server startup, so edits don't apply until it restarts.

`--browser firefox` uses Playwright's own bundled Firefox, sidestepping the missing
system-Chrome problem. (Edge via `"--channel", "msedge"` also works on Windows.)

## Workflow

### 1. Open the recipe (and confirm login)

Navigate to the user's URL with `browser_navigate`. A headed Firefox window opens.
Take a snapshot or evaluate `document.body.innerText` and check for a paywall /
"Subscribe" wall instead of the recipe. If the user isn't logged in, ask them to log
into NYT Cooking in the Firefox window, then continue. The Playwright profile is
persistent, so login normally sticks across runs.

### 2. Extract everything in one call

Pull the recipe fields, the flattened steps, the image crops, and the tip text in a
**single** `browser_evaluate` — one browser round-trip, and nothing can drift out of
sync. Three things to know about why this snippet is shaped the way it is:

- **Steps are nested inconsistently.** Some are plain `HowToStep` objects (`.text`);
  others are wrapped in a `HowToSection` whose `.itemListElement` is a `HowToStep`.
  The recursive `walk` flattens both into one ordered list.
- **The tip is NOT in the JSON-LD.** NYT "Tip"/"Tips" notes only exist in the
  rendered page, so we grab a slice of `body.innerText` near the word "Tip" and let
  you lift the real sentence(s) out of it afterward.
- **Images come as several crops.** We return them so you can pick the largest
  landscape in step 4.

```js
() => {
  const scripts = [...document.querySelectorAll('script[type="application/ld+json"]')];
  let data = null;
  for (const s of scripts) {
    try {
      let d = JSON.parse(s.textContent);
      if (Array.isArray(d)) d = d.find(x => x['@type'] === 'Recipe') || d[0];
      const t = d['@type'];
      if (t === 'Recipe' || (Array.isArray(t) && t.includes('Recipe'))) { data = d; break; }
    } catch (e) {}
  }
  if (!data) return 'NO_RECIPE_JSONLD';
  const steps = [];
  const walk = (n) => {
    if (!n) return;
    if (Array.isArray(n)) return n.forEach(walk);
    if (n['@type'] === 'HowToStep' && n.text) steps.push(n.text.trim());
    else if (n['@type'] === 'HowToSection') walk(n.itemListElement);
  };
  walk(data.recipeInstructions);
  const bt = document.body.innerText;
  const ti = bt.search(/\bTips?\b/);
  const tipBlock = ti >= 0 ? bt.slice(ti, ti + 600) : 'NO_TIP';
  const images = (Array.isArray(data.image) ? data.image : [data.image]).filter(Boolean)
    .map(i => ({ url: i.url || i.contentUrl || i, w: parseInt(i.width) || 0 }));
  return JSON.stringify({
    name: data.name, author: data.author && data.author.name, yield: data.recipeYield,
    totalTime: data.totalTime, category: data.recipeCategory, keywords: data.keywords,
    diet: data.suitableForDiet, description: data.description,
    ingredients: data.recipeIngredient, steps, images, tipBlock
  });
}
```

Then interpret the result:

- `totalTime` is ISO-8601 (`PT0H30M` → render as "30 minutes").
- `tipBlock` is raw page text. If it's `NO_TIP`, there's no tip — skip the callout in
  step 5. Otherwise lift just the actual tip sentence(s) and stop before unrelated
  sections like "Similar Recipes".
- `tags` come from `keywords` (and `diet`, e.g. add `vegetarian` only when
  `suitableForDiet` says so) — lowercase, pick the useful few.

### 3. Pick the destination folder

Match the recipe to an existing top-level folder using `recipeCategory` / `keywords`
and judgment. Current folders: **Baking, BBQ, Beef, Chicken, Mexican, Noodles,
Pasta, Pizza, Sides, Sous Vide, Vegetarian**. Use `Incoming` only as a last resort.
Notes:
- Long pasta (spaghetti, linguine) → `Pasta`; Asian noodles (ramen, udon, lo mein) → `Noodles`.
- A meat-forward main goes by its protein (`Beef`, `Chicken`) even if it's a stew or stir-fry.
- If two folders fit, pick the most specific and mention the choice so the user can move it.

### 4. Download the lead image

The JSON-LD `image` array has several crops. Prefer the **largest landscape** for a
header banner — typically the `...videoSixteenByNineJumbo1600.jpg` URL (1600×900);
otherwise take the widest `contentUrl`/`url`. Save it into an `attachments/`
subfolder beside the note, named after the recipe. Send a User-Agent or the CDN may
refuse:

```bash
cd "<vault>/<Folder>" && mkdir -p attachments && \
curl -sSL -A "Mozilla/5.0" -o "attachments/<Recipe Name>.jpg" "<image url>"
```

Verify it's a real image (non-trivial size, `file` reports JPEG/PNG) before
embedding. If there's no image, just skip the embed.

### 5. Write the note

Create `<Folder>/<Recipe Name>.md` following `Templates/Recipe.md`, with the image
embedded at the very top. Match the vault's existing recipes: a YAML frontmatter
block, then the embed, then `# Title`, the overview paragraph, and the
`### 🛒 Ingredients` / `### 🥣 Steps` sections.

```markdown
---
tags: [<from keywords/diet, lowercase, e.g. pasta, vegetarian, quick>]
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

Guidance:
- `date` uses today's date in the template's `YYYY-MM-DD dddd` format (e.g. `2026-05-28 Thursday`), not the recipe's publish date.
- Keep ingredient and step text verbatim from the source; just trim stray whitespace and fix obvious artifacts (e.g. a lone "(in a food processor..." → "(In a food processor...").
- Embed the image with `![[attachments/<Recipe Name>.jpg]]` — an Obsidian wikilink embed, consistent with the `obsidian-markdown` skill.
- Drop the `> [!tip]` callout entirely if there's no tip.

### 6. Report back

Tell the user the note path, the image path, the folder you chose (and why, if it
was a close call), and any judgment calls — so they can move or retag if they
disagree.

## Notes on robustness

- If `browser_evaluate` returns `NO_RECIPE_JSONLD`, the page may not have finished
  loading or the URL isn't a recipe page — re-navigate, wait, and retry before
  falling back to scraping the visible DOM.
- A full-page `browser_snapshot` on NYT can exceed the tool's output limit; prefer
  targeted `browser_evaluate` calls (JSON-LD, specific text) over big snapshots.
- Filenames: keep the recipe's natural title (spaces are fine in this vault). Strip
  characters illegal on the filesystem (`\ / : * ? " < > |`) if the title contains them.
```
