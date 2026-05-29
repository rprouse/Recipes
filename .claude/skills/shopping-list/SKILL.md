---
name: shopping-list
description: >
  Work with the user's Bring! shopping lists via the bring-mcp MCP server: list
  items, add items (with optional quantity or type details), and remove items.
  Use this skill whenever the user mentions their shopping list, grocery list, or
  Bring!, or asks to see what's on the list, add something to buy, or cross
  something off — e.g. "what's on my shopping list", "add milk", "put 2 dozen eggs
  on the list", "remove bread", "did we already have cheese on there". Always
  operates on the default list unless the user names a different one.
---

# Shopping List (Bring!)

Manage the user's Bring! shopping lists through the `bring-mcp` tools. The user's
lists are stored in German/Swiss German (e.g. `Käse`, `Rahm`, `Zucchetti`) and are
often shared with a partner, so two rules are constant: **always show items in
English**, and when **adding** items, map them to the catalog's German name so they
match existing entries, categories, and icons on the shared list.

## Picking the list

Default to the user's default list on every operation unless they explicitly name
another one.

- Default list: call `getDefaultList` to get its `listUuid`.
- A named list ("the cabin list", "Mom's list"): call `loadLists`, match the name,
  and use that `listUuid` instead.

Cache the `listUuid` for the rest of the conversation rather than re-fetching it
each turn.

## Translations

The list is stored in German. Maintain an English view by calling
`loadTranslations` (locale `en-US`) which returns a `{ German: English }` lookup
table. Use it in both directions:

- **Displaying** (German → English): look up each item name in the table.
- **Adding** (English → German): reverse-lookup the user's English word to its
  German catalog name so it lands on the shared list cleanly.

Call `loadTranslations` once per conversation and reuse the table. If an item isn't
in the table (e.g. a brand like `Nuun`), leave the name as-is and show it verbatim.

## Listing items

1. Resolve the `listUuid` (see *Picking the list*).
2. Call `getItems` with that `listUuid`. The response has two arrays: `purchase`
   (the active list) and `recently` (recently used / removed items).
3. Call `loadTranslations` and translate every `name` to English.
4. Show the `purchase` items as a clean English bullet list. Include the
   `specification` in parentheses when present (e.g. "Tomatoes (Roma, 5)").
5. Only mention `recently` if the user asks what was recently on the list or wants
   suggestions to re-add.

## Adding items

Use `specification` for any quantity, count, or type detail — keep the core item in
`itemName` and the detail in `specification` (e.g. `itemName: "Milch",
specification: "2 L"`). Reverse-translate the English item to its German catalog
name before saving.

- **One item:** `saveItem` with `itemName`, `listUuid`, and optional
  `specification`.
- **Several items at once:** `saveItemBatch` with an `items` array of
  `{ itemName, specification }`. Prefer this over multiple `saveItem` calls.

After adding, confirm in English what went on the list (with the detail if given).
A successful `saveItem` may return an empty string — that is normal, not an error.

**Examples:**

Input: "add milk"
Action: `saveItem(itemName="Milch", listUuid=…)` → "Added Milk to your list."

Input: "put 2 litres of cream and a dozen eggs on the list"
Action: `saveItemBatch(items=[{itemName:"Rahm", specification:"2 L"},
{itemName:"Eier", specification:"12"}], listUuid=…)` → "Added Cream (2 L) and Eggs
(12)."

Input: "add Nuun" (no German equivalent)
Action: `saveItem(itemName="Nuun", listUuid=…)` → "Added Nuun."

## Removing items

Removing takes the item off the active `purchase` list (Bring! moves it to
`recently`). Match the user's English word to the stored German item name first.

- **By name (preferred, most robust):** `deleteMultipleItemsFromList` with an
  `itemNames` array — works for one or many items.
- **By id:** `removeItem` / `moveToRecentList` take an `itemId`. Item ids equal the
  item name in this data, so name-based deletion is usually simpler.

If the user's item isn't on the current list, say so rather than guessing at a
near-match. Confirm what was removed in English afterward.

## After any change

When the user has added or removed several things, or asks, re-display the updated
list in English so they can see the current state. For a single quick add or
remove, a one-line English confirmation is enough.

## Notes

- A list with `"status": "SHARED"` is shared with another person; changes are
  visible to them immediately. Don't treat that as a problem, just be aware edits
  aren't private.
- Never delete or clear the whole list in one shot unless the user explicitly asks
  for exactly that, and confirm first.
