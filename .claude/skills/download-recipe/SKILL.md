---
name: download-recipe
description: >-
  Download a recipe from ANY cooking website (Serious Eats, AllRecipes, Bon
  Appétit, Food Network, Smitten Kitchen, food blogs, etc.) and save it into this
  Obsidian recipe vault as a formatted note, lead image and all. Use this whenever
  the user gives a recipe URL and wants it saved, imported, clipped, grabbed, or
  added to the vault — "save this recipe", "add this to my recipes", "import this
  recipe", "clip this". The user supplies the URL; this skill does NOT invent a
  recipe. IMPORTANT: for cooking.nytimes.com URLs use the `download-nyt-recipe`
  skill instead (it reads NYT's structured data directly) — this skill is for
  every OTHER site.
---

# Download a web recipe into the vault

Turns a recipe URL into a finished vault note: correct folder, frontmatter
following `Templates/Recipe.md`, an overview paragraph, ingredients, steps, an
optional cook's tip, and the lead photo embedded at the top (downloaded to an
`attachments/` subfolder beside the note).

This is the **generic** counterpart to `download-nyt-recipe`. NYT Cooking ships a
clean `schema.org/Recipe` JSON-LD that that skill parses directly; arbitrary sites
vary too much for one parser, so here we extract readable content with **Defuddle**
and exercise judgment to map it onto the vault's note shape.

## Workflow

### 1. Confirm this is the right skill

If the URL is on `cooking.nytimes.com`, stop and use `download-nyt-recipe` instead
— it gets cleaner structured data for that site. Otherwise continue.

### 2. Extract the page with Defuddle

Defuddle strips nav/ads/clutter and returns clean markdown — far fewer tokens than
raw HTML, and it preserves the recipe's ingredients, steps, times, yield, author,
and image links. See the `defuddle` skill for details; the essentials:

```bash
defuddle parse "<recipe url>" --md
```

If the command fails with **exit code 127** (`defuddle: command not found`), install
it once, then retry: `npm install -g defuddle`. (The binary is `defuddle`.)

Read the output and pull out: recipe **name**, **author/source**, **yield/servings**,
**times** (prep/cook/total), the **overview/intro**, **ingredients**, **steps**, any
**tips/notes**, and the **lead image URL** (usually the first content image).

If Defuddle returns little or garbled content (some sites block it or render the
recipe only in JavaScript), fall back to fetching the raw HTML and reading its
`<script type="application/ld+json">` `Recipe` block — most recipe sites ship one,
just like NYT. As a last resort, use `WebFetch` on the URL.

### 3. Pick the destination folder

Map the recipe to a top-level folder using the **folder rubric** documented in the
`download-nyt-recipe` skill (`.claude/skills/download-nyt-recipe/SKILL.md`, the
"Folder rubric" section) — it's the single source of truth so the two importers
file recipes identically. The short version: dish type (Pasta, Noodles, Soups,
Salads, Pizza, Baking, Desserts, Breakfast…) wins over protein (Beef, Chicken,
Pork, Seafood); cuisine (Mexican) and method (BBQ, Sous Vide) apply only when
that's the defining trait. Mention any close call so the user can move it.

### 4. Match the note format to a real neighbor note

Don't write from `Templates/Recipe.md` alone — that stub omits fields the real notes
carry. **Read an existing note in the target folder** and mirror its frontmatter
exactly. In practice the live notes use:

```
tags, title, author, servings, time, date, link, image
```

(`image:` and `title:` are present in real notes even though the bare template drops
them.) When in doubt, copy the neighbor's field order and quoting.

### 5. Download the lead image

Save the main photo beside the note, named after the recipe. A User-Agent header
avoids CDNs that refuse bare requests; prefer the largest available crop:

```bash
cd "G:/My Drive/Recipes/<Folder>" && mkdir -p attachments && \
curl -sSL -A "Mozilla/5.0" -o "attachments/<Recipe Name>.jpg" "<image url>"
```

Verify it's a real image (`file` reports JPEG/PNG, non-trivial size). Skip the embed
if the page has no usable image rather than embedding a broken link.

### 6. Write the note

Write `<Folder>/<Recipe Name>.md`, image embedded at the very top, following the
neighbor note's shape:

```markdown
---
tags: [<folder>, <descriptors: quick, weeknight, vegetarian, the cuisine…>]
title: <Recipe Name>
author: <author or source site>
servings: <e.g. 8 to 10 servings>
time: <human text — capture multi-stage spans sensibly, see below>
date: <today as YYYY-MM-DD dddd, e.g. 2026-06-15 Monday>
link: <recipe URL>
image: "[[attachments/<Recipe Name>.jpg]]"
---

![[attachments/<Recipe Name>.jpg]]

# <Recipe Name>

<overview paragraph — a tightened version of the intro, in the author's spirit>

### 🛒 Ingredients
- <each ingredient, verbatim; keep amounts and parentheticals>

### 🥣 Steps
1. <each step, in order; keep temperatures and times>

> [!tip] Tip
> <synthesize from the page's tips/notes; DROP this callout entirely if none>
```

Conventions that matter:
- **`date` is today**, in `YYYY-MM-DD dddd` format — the date you're adding it, not
  the recipe's publish date.
- **`time`** is human text. For a long, multi-stage recipe, prefer an honest span
  (`15 min prep + 24–72 hr sous vide + 2–3 hr finish`) over a single misleading
  total. Leave blank if the page gives nothing.
- **First tag mirrors the folder** (lowercase); add genuinely useful descriptors.
- Keep ingredient/step text faithful — trim whitespace and strip the inline ad/link
  cruft Defuddle sometimes leaves, but don't paraphrase quantities or temperatures.
- The page may bury useful guidance (a temperature/time table, a "buy the fatty cut"
  warning) in prose or a notes section — fold the important bits into the tip callout
  so they aren't lost.
- `![[attachments/<Name>.jpg]]` is an Obsidian wikilink embed (see `obsidian-markdown`).
- **Filename:** keep the natural title (spaces are fine); strip only filesystem-illegal
  characters (`\ / : * ? " < > |`). If a *different* recipe already owns that filename,
  disambiguate by appending the author: `<Name> - <Author>.md`.

### 7. Preserve LF and report back

This vault pins LF line endings (`core.autocrlf false`). Confirm the new note has no
carriage returns before finishing:

```bash
grep -c $'\r' "<Folder>/<Recipe Name>.md"   # expect 0
```

Then report the note path, the image path, the folder chosen (and why, if it was a
close call), and any judgment calls — e.g. how you condensed the `time`, what you put
in the tip, or fields the source didn't provide.

**Don't commit.** The user backs up the vault themselves via the obsidian-git
keybindings; files sync to Google Drive on their own.
