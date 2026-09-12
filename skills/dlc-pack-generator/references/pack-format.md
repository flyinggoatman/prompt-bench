# Prompt Bench DLC format notes

These notes are a compact operating reference for the skill. The repository README and runtime code remain the source of truth. For field-by-field JSON structures and examples for every importable mechanic, also read `mechanics.md`.

## Recognised top-level keys

`pack`, `private`, `shared`, `masters`, `people`, `categories`, `dials`, `variation`, `fields`.

Prompt Bench does not have special top-level `style` or `genre` keys. Style and genre DLC must therefore be emitted as normal `categories` entries. This skill uses `STYLE` (order 22) and `GENRE` (order 28), which the generic category loader supports.

## Masters

A master is an object with `id`, `name`, `blurb`, and `body`; `inherits` is optional. Existing repository masters are `A`, `B`, `C`, and `D`. Keep generated IDs to one character because module suitability is encoded in the compact `m` string. `*` means an item suits every master.

## Categories

A category has `key`, optional `label`, `note`, `order`, `replace`, and `items`. Each item is `{ "m": "...", "t": "..." }`. If the same category key appears in multiple packs, items are merged. Exact duplicate `t` text is deduplicated and the master tags are merged, so duplicate text can silently reduce a requested variation count.

Avoid `"replace": true` for generated DLC unless the user explicitly asks to wipe an existing category.

## Controls and other mechanics

Prompt Bench also imports `shared` prompt blocks, `people`, `dials`/sliders, `variation` pools used by Vary, and free-text `fields`. Their complete structures, modifiers, merge behaviour and examples are defined in `mechanics.md`.

Selectable time/weather belongs in the existing `CONDITIONS` category (order 64). Random time changes belong in a `variation` pool. Sliders belong in `dials`.

## File behaviour

Pack files are merged in filename order. Numeric filename prefixes therefore make the generated set deterministic. Server uploads must be UTF-8 JSON objects, are limited to 512 KB per file, and must contain at least one recognised key. The helper splits oversized style/genre collections into numbered pack files before that limit is reached.

## Writing guidance

Write modules as positive, concrete instructions. Prefer specific visual evidence, materials, composition, setting, action, lighting, texture, period cues, and genre conventions over vague adjectives. Do not fill a large requested count with near-duplicates or trivial wording changes.
