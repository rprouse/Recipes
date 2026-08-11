# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

An **Obsidian vault of cooking recipes** — not a software project. There is no build, test, or lint step. Content is Markdown notes; "working in this repo" means creating, editing, organizing, and tagging recipe notes.

- The vault lives at `G:\My Drive\Recipes`, so it **syncs through Google Drive** — files may change under you, and anything written here (especially images) syncs to the cloud.
- Backups are git commits made by the **obsidian-git** plugin (commit messages look like `vault backup: <timestamp>`). Other plugins in use: `obsidian-icon-folder`, `obsidian-paste-image-rename`, `recent-files-obsidian`.
- Line endings are pinned to LF (`git config core.autocrlf false`, `core.eol lf`) so the vault behaves across Windows/Linux. Preserve LF when writing files.
- A **PostToolUse formatter hook may rewrite notes after Edit/Write**. Re-Read the file before a follow-up edit that targets a region it might have reformatted.
- `git commit` must go through the **PowerShell tool**, not Bash (1Password SSH signing breaks under MSYS2) — see the global `~/.claude/CLAUDE.md` for the full reason. The user normally commits themselves via the obsidian-git keybindings; don't commit unless asked.

## Recipe note conventions

Every recipe note follows `Templates/Recipe.md`. Match this structure exactly when creating notes:

```markdown
---
tags: [<folder>, <descriptors like quick, weeknight, vegetarian>]
title: <Recipe Name>
author: <author, if known>
servings: <e.g. 4 servings>
time: <human text, e.g. 35 minutes — may be blank>
date: <YYYY-MM-DD dddd, e.g. 2026-05-28 Thursday>
link: <source URL>
---
![[attachments/<Recipe Name>.jpg]]

# <Recipe Name>

<overview paragraph>

### 🛒 Ingredients
- ...

### 🥣 Steps
1. ...

> [!tip] Tip
> <optional cook's tip>
```

Conventions that matter:
- The lead image is embedded at the very top via an Obsidian wikilink and stored in an **`attachments/` subfolder beside the note** (per-folder, e.g. `Chicken/attachments/...`), not a single vault-wide folder.
- `date` is the date the note was added, in `YYYY-MM-DD dddd` format — not the recipe's publish date.
- `tags` are a lowercase inline list; the first tag mirrors the folder, lowercased and hyphenated for multi-word folders (`Sous Vide/` → `sous-vide`). Editing tags means rewriting the single `tags: [...]` line.
- Drop the `> [!tip]` callout when there's no tip.
- **Original recipes** (written from scratch, no source URL) keep `author:`, `link:` and `image:` present but blank rather than omitted, so the properties still appear in Obsidian's property editor.
- **Never use em dashes (—) in recipe prose you write.** Use a comma, a colon, parentheses, or split the sentence. This covers the overview, steps and callouts of any note authored here. Text carried over verbatim from a downloaded recipe keeps whatever punctuation the source used.

## Folder taxonomy

Recipes are filed into mixed-axis top-level folders — by **protein** (Beef, Chicken, Pork, Seafood), **dish type** (Pasta, Noodles, Pizza, Soups, Salads, Sandwiches, Baking, Breakfast, Desserts, Snacks, Sides, Drinks), **cuisine** (Mexican), **method** (BBQ, Sous Vide), **diet** (Vegetarian), or **occasion** (Camping, Sports). `Incoming/` is the unsorted inbox.

When classifying, dish type wins over protein (e.g. "Shrimp Piccata Spaghetti" → Pasta, not Seafood); soups/stews → Soups even when meat-forward. The full rubric lives in the `download-recipe` skill.

## Reference notes (not recipes)

`Reference/` holds a growing series of **general cooking-knowledge notes** — ingredient guides, techniques, cuisine flavor profiles — linked from a hub note (`Reference/Cooking Reference.md`). These are **not recipes**: do not apply `Templates/Recipe.md` to them. To create or extend one, use the **`create-reference-guide` skill** (`.claude/skills/create-reference-guide/`), which carries the house format and hub-linking steps.

## Camping recipes

`Camping/` holds trail and backpacking food and uses **`Templates/Camping Recipe.md`**,
which extends the standard template with `weight-per-serving` (grams, numeric),
`calories-per-serving`, `water-needed` (millilitres, numeric — `0` means no water
needed, blank means unknown), and `cook-method`. `Camping.base` renders these,
sorted by pack weight. The camping folder wins over dish type: "Hiker Pasta" is
Camping, not Pasta. Distinct from `Sports/`, which is sports drinks and exercise
nutrition. Lead images from Outdoor Eats are **800×800 PNG**, so imports from there
use `.png` in the attachment filename, the `image:` property, and the embed. That
follows the source, not a folder rule: match whatever the actual file is
(`Pad Thai.jpg` and `Bacon Cheddar Grits w Eggs.jpg` already use `.jpg`).
`Camping.base`'s **No-Cook view filters `cook-method == "no-cook"` as an exact
string**, so "cold soak" or "No-Cook" silently drops the note out of that view.

## Lead images for original recipes

A from-scratch recipe has no source photo, and a missing `image:` renders a blank card. Wikimedia Commons is the working source: query `commons.wikimedia.org/w/api.php` with `generator=search&gsrnamespace=6&prop=imageinfo&iiprop=url|extmetadata`, then read `LicenseShortName`. **Prefer CC0**; CC BY and CC BY-SA are usable but need a credit line at the foot of the note. Commons returns 429 if hit too fast, so space the requests out.

## Recipe import tooling

One skill handles every site: the **`download-recipe` skill** (`.claude/skills/download-recipe/`) — invoke it for any recipe URL, NYT Cooking included. Key facts:

- **No login is needed for a single recipe** on most sites, even behind a paywall — they gate the *rendered reading experience*, not the `schema.org/Recipe` JSON-LD they publish for SEO, so a plain fetch gets the whole recipe. **Outdoor Eats is the exception**: it gates server-side, so a locked page has no recipe in it at all and the extractor exits 2 rather than writing an empty note.
- Extraction is `scripts/recipe_extract.py`, run with **`uv run`** — a PEP 723 header declares `recipe-scrapers`, so uv resolves it automatically and there is nothing to `pip install`. The script emits normalized JSON; the note itself is written with editorial judgment, not generated.
- **Dotdash Meredith sites (Serious Eats, Simply Recipes, AllRecipes, Food & Wine) return intermittent 403s** to automated clients. It is rate-limiting, not fingerprinting — the same URL alternates 200/403 seconds apart regardless of HTTP client. The script retries with backoff; if it still fails, wait and re-run.
- The `link:` frontmatter field contains the source URL, and for NYT the recipe id in it acts as the **stable join key** between NYT data and a vault note — used to dedupe imports and to tag existing notes (e.g. matching a collection's recipes to add a `make-again` tag). Match on `recipes/<id>-` (with trailing hyphen) to avoid id-prefix false positives.
- **`image:` frontmatter is load-bearing**, not decorative: `All Recipes.base` and `Make Again.base` render their card views via `image: note.image`, so a note missing it shows a blank card. Every note with a lead photo needs both the `image:` property and the embed below the frontmatter.

`.recipe-import/` (gitignored, along with `.playwright-mcp/`) holds leftover scratch from the original 853-recipe NYT bulk import — a per-recipe JSON cache and the one-off `add_image_frontmatter.py` backfill. Nothing current depends on it.
