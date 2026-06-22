# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

An **Obsidian vault of cooking recipes** — not a software project. There is no build, test, or lint step. Content is Markdown notes; "working in this repo" means creating, editing, organizing, and tagging recipe notes.

- The vault lives at `G:\My Drive\Recipes`, so it **syncs through Google Drive** — files may change under you, and anything written here (especially images) syncs to the cloud.
- Backups are git commits made by the **obsidian-git** plugin (commit messages look like `vault backup: <timestamp>`). Other plugins in use: `obsidian-icon-folder`, `obsidian-paste-image-rename`, `recent-files-obsidian`.
- Line endings are pinned to LF (`git config core.autocrlf false`, `core.eol lf`) so the vault behaves across Windows/Linux. Preserve LF when writing files.
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
- `tags` are a lowercase inline list; the first tag mirrors the folder. Editing tags means rewriting the single `tags: [...]` line.
- Drop the `> [!tip]` callout when there's no tip.

## Folder taxonomy

Recipes are filed into mixed-axis top-level folders — by **protein** (Beef, Chicken, Pork, Seafood), **dish type** (Pasta, Noodles, Pizza, Soups, Salads, Sandwiches, Baking, Breakfast, Desserts, Snacks, Sides, Drinks), **cuisine** (Mexican), **method** (BBQ, Sous Vide), or **diet** (Vegetarian). `Incoming/` is the unsorted inbox.

When classifying, dish type wins over protein (e.g. "Shrimp Piccata Spaghetti" → Pasta, not Seafood); soups/stews → Soups even when meat-forward. The full rubric lives in the `download-nyt-recipe` skill.

## NYT Cooking import tooling

Most notes were imported from NYT Cooking. The reusable tooling is the **`download-nyt-recipe` skill** (`.claude/skills/download-nyt-recipe/`) — invoke it for any NYT recipe URL or to bulk-import the user's recipe box. Key facts baked into that skill:

- A **single recipe needs no login**: its full `schema.org/Recipe` JSON-LD (and the cook's tip, in a separate embedded blob) is in the raw HTML, so a plain `curl` gets everything. The Playwright browser is only needed to enumerate the auth-gated recipe box.
- The recipe box is enumerated via the JSON API `…/api/v2/users/<USER_ID>/search/recipe_box_search?q=&per_page=48&page=N` (add `&collection_id=<id>` for a specific collection/folder).
- Bulk pipeline (all resumable): enumerate (browser) → `scripts/nyt_fetch.py <manifest.json>` (curl+parse, no browser) → classify folders with **Sonnet** sub-agents → `scripts/nyt_write.py` (writes notes + downloads images).
- The `link:` frontmatter field contains the NYT recipe id, which acts as the **stable join key** between NYT data and a vault note — used to dedupe imports and to tag existing notes (e.g. matching a collection's recipes to add a `make-again` tag). Match on `recipes/<id>-` (with trailing hyphen) to avoid id-prefix false positives.

Working scratch for imports (manifests, per-recipe JSON cache, batch files, logs) goes in **`.recipe-import/`**, which is gitignored along with `.playwright-mcp/`. The committed, canonical scripts are the ones bundled in the skill — copy/run those rather than relying on scratch.
