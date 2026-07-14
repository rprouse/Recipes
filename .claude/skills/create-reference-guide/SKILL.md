---
name: create-reference-guide
description: >-
  Create a general cooking-knowledge reference note in the vault's Reference/
  folder — ingredient guides, technique references, flavor/cuisine cheat sheets,
  and other kitchen know-how that isn't a recipe. Use whenever the user wants a
  reference/info page about cooking rather than a specific dish: "make a page on
  X", "add a guide to X", "create a reference for X", "I want a cheat sheet on
  X", or asks about types of an ingredient and what each is best for, storage,
  substitutions, conversions, doneness temperatures, smoke points, cuisine flavor
  profiles, and the like. These notes are NOT recipes — do not use
  Templates/Recipe.md for them. Also use when the user asks to add another note
  to the Reference/ series or extend the "Cooking Reference" collection.
---

# Create a Reference guide

The vault's `Reference/` folder holds a growing series of **general cooking-knowledge
notes** — the durable stuff that isn't tied to one dish: ingredient guides (potato
types, salt, oils), techniques (meat doneness temps), and flavor references (cuisine
profiles). They're linked from a hub note so the collection stays browsable.

These are **reference notes, not recipes.** Do not apply `Templates/Recipe.md`, its
frontmatter, or its `🛒 Ingredients` / `🥣 Steps` structure — that template is only
for actual dishes. A reference note is a scannable knowledge page.

## When you're asked for one of these

Figure out which kind of guide it is (ingredient / technique / cuisine-flavor / other
kitchen reference) — this decides the hub section later — then write the note and link
it. If the user asks for something dish-specific ("a recipe for X"), this is the wrong
skill; use `download-recipe` / `download-nyt-recipe` or the Recipe template instead.

## Note format

Match the house style of the existing notes exactly — consistency is what makes the
series usable, since you can scan the same structure across every guide. Write LF line
endings (the vault is pinned to LF).

Save to `Reference/<Title>.md`. Use a clear, human title as the filename (e.g.
`Cooking Oils.md`, `Herbs — Fresh vs Dried.md`); wikilinks resolve by filename, so it
doesn't matter that it lives in a subfolder.

````markdown
---
tags: [reference, <topic>, <more topic tags>]
title: <Title>
date: <YYYY-MM-DD dddd>
---
# <emoji if it fits> <Title>

> Part of [[Cooking Reference]]

<one short intro paragraph: the core organizing idea. For most guides this is the
single most useful mental model — e.g. potatoes sort by starch content, herbs by
hardy-vs-tender, oils by smoke point. Lead with that so the table makes sense.>

| <Type / Item> | <Names / Varieties> | <Best Uses> |
| --- | --- | --- |
| ... | ... | ... |

### <emoji> Key tips
- <the non-obvious things a cook actually needs — ratios, timing, common mistakes>

### 🗄️ Storage
- <include only when storage is relevant to the topic — ingredients yes, doneness
  temps no>

> [!tip] Rule of thumb
> <one-line heuristic that captures the whole page — the "if you remember nothing
> else" takeaway>
````

Conventions that matter:
- **First tag is always `reference`**, followed by topic tags (e.g. `[reference, oils, fats, ingredients]`). This keeps the series cleanly separated from recipe notes in searches and Bases.
- **`date`** is today's date the note is added, in `YYYY-MM-DD dddd` format (same as recipe notes) — e.g. `2026-07-13 Monday`.
- **The `> Part of [[Cooking Reference]]` backlink** goes right under the H1 so every note points home.
- The **main table** is the heart of the page. Adapt the columns to the topic, but keep it a table — that's the format the series is built around.
- **Drop sections that don't apply.** Storage makes sense for ingredients, not for a temperature chart. Don't pad.
- **Be honest about approximation.** Smoke points, salt densities, cuisine generalizations, etc. vary — hedge them ("approx.", a `> [!warning]` for broad-strokes pages) rather than stating false precision. The user cooks from these; misplaced confidence is worse than a caveat.
- Aim for genuinely useful, opinionated content — the tips and rule-of-thumb are where the value is, not the obvious facts.

## Update the hub

After writing the note, add a one-line link to the hub `Reference/Cooking Reference.md`
so the collection stays connected. Put it under the section that fits:

- **Ingredient Guides** — a single ingredient or ingredient family (potatoes, salt, oils, herbs, onions)
- **Techniques** — methods and how-tos (doneness temperatures, knife skills, braising)
- **Cuisines & Flavor** — flavor profiles, spice blends, regional pantry references
- **Kitchen Reference** — everything else (conversions, substitutions, equipment)

Format each link as `- [[Note Title]] — <short hook describing what it covers>`. If a
fitting section doesn't exist yet, add it (keep the section order sensible). The hub is
a Map of Content tagged `[reference, moc]`.

## Don't commit

Like the rest of the vault, these files sync via Google Drive and the user commits
themselves through obsidian-git. Create the files and stop — don't run `git commit`
unless asked.
