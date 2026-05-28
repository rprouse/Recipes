---
name: move-incoming
description: >-
  Triage the vault's Incoming/ folder — read each note that has landed there and
  move it to the appropriate recipe folder, aligning its tags to the vault
  convention. Use whenever the user says "go through Incoming", "sort/file/clear
  my incoming recipes", "move the incoming recipes to folders", "organize the
  inbox", "empty the Incoming folder", or otherwise wants the Incoming/ backlog
  filed. Works on whatever notes are currently in Incoming/ — the user does not
  need to name them.
---

# Triage and file the Incoming/ folder

`Incoming/` is the vault's inbox: recipe notes (often imported from YouTube or other
AI agents) get dropped there for later sorting. This skill reads each one and moves
it to the right top-level recipe folder, fixing its tags on the way.

## Workflow

### 1. List what's in Incoming/

```bash
ls -1 "Incoming/"
```

### 2. Read each note and decide: recipe, or not?

Read the note. **Do not move non-recipe notes.** In particular, leave
`Incoming Recipes.md` (or any note whose body just explains the folder, e.g. "Recipes
will automatically be dropped in this folder…") in place — it's the inbox's purpose
marker, not a recipe. A real recipe has ingredients/steps; an index/placeholder/README
note does not.

### 3. Pick the destination folder

Classify by the same rubric the import tooling uses (full version in the
`download-nyt-recipe` skill). Existing folders: **Baking, BBQ, Beef, Chicken,
Desserts, Drinks, Mexican, Noodles, Pasta, Pizza, Pork, Salads, Seafood, Sides,
Snacks, Soups, Sous Vide, Vegetarian** (plus **Breakfast**). Priority:

1. Dish type first: pasta → Pasta; ramen/soba/udon/rice-noodle → Noodles; soup/stew/
   chili/broth → Soups; salad → Salads; pizza → Pizza; Mexican (tacos/enchiladas) →
   Mexican; breakfast food → Breakfast; bread/cracker → Baking; dessert → Desserts;
   beverage → Drinks; snack bar → Snacks.
2. Else by primary protein: Beef, Chicken (incl. turkey), Pork, Seafood.
3. **Condiment / sauce / ferment / dressing / slaw / pickle / spice-paste → Sides.**
   (This is where chili crisp, kimchi, dressings, etc. go.)
4. Meatless main with no better home → Vegetarian. BBQ / Sous Vide only if explicitly
   that method.

When a dish is both a dish-type and a protein (e.g. "Shrimp Piccata Spaghetti"), dish
type wins.

**Multi-dish collections** (one note containing many recipes, e.g. "15 Medieval
Meals") have no perfect single home — pick the folder that fits the *dominant* content
(count the dishes by type/ingredient), file it there, and **tell the user it was a
judgment call** with the runner-up, so they can redirect.

### 4. Move the note (and its image, if any)

Use a plain `mv` — the obsidian-git plugin will pick up the rename; do not `git mv` or
commit (the user commits themselves).

```bash
mv "Incoming/<Note>.md" "<Folder>/"
```

If the note embeds an image (`![[attachments/<X>.jpg]]`), move that file too so the
embed keeps resolving, and create the target `attachments/` dir if needed:

```bash
mkdir -p "<Folder>/attachments" && mv "Incoming/attachments/<X>.jpg" "<Folder>/attachments/"
```

**Filename collision:** if `<Folder>/<Note>.md` already exists and is a *different*
recipe (its source link/id isn't in that file), don't overwrite — append the author or
a distinguisher to the moved file's name (e.g. `<Note> - <Author>.md`).

### 5. Align the tags to the vault convention

Vault convention: the **first tag mirrors the folder** (lowercased, spaces → hyphens,
e.g. `Sous Vide` → `sous-vide`). Many inbox notes (especially YouTube imports) don't
follow this. Prepend the folder tag to the existing inline `tags: [...]` line, keeping
the note's original descriptive tags:

- `tags: [chili, homemade, condiment]` in `Sides/` → `tags: [sides, chili, homemade, condiment]`

Don't duplicate if the folder tag is already present.

### 6. Report

List each move (note → folder), call out any judgment calls (collections, close
calls) with the alternative folder, note anything left in Incoming/ and why, and that
the changes are uncommitted for review.
