---
name: dlc-pack-generator
description: Generate, validate, package, and deliver Prompt Bench DLC packs using every native importable mechanic, including masters, categories, dials, variation pools, fields, people, shared blocks, and scalable style/genre sets.
---

# Prompt Bench DLC Pack Generator

Use this skill when a user asks for a new Prompt Bench DLC, expansion, master, category/module set, slider, Vary pool, field, cast/shared pack, style pack, genre pack, or a large themed set of prompt variations.

## Source of truth

Before authoring, inspect the current Prompt Bench repository when repository access is available. At minimum read:

- `README.md`, especially **Pack file format**, **DLC packs**, and **A note on writing modules**.
- representative files in `packs/masters/`, `packs/categories/`, `packs/controls/`, `packs/dlc/`, and `packs/dlc2/`.
- `packs/dlc/00-master-sequence.json` for inheritance.
- `packs/dlc/64-conditions.json` for weather/time modules.
- `packs/controls/10-dials.json`, `20-variation.json`, and `30-fields.json` for interactive controls.
- the current loader/validation code in `prompt-bench.html` and `server.py` when compatibility rules may have changed.

Do not assume bundled references outrank the live repository. Read:

- `references/pack-format.md` for compact compatibility rules.
- `references/mechanics.md` for the complete structural recipe for every importable Prompt Bench mechanic.

## Complete mechanic coverage

The skill must be able to author **every importable Prompt Bench mechanic**, not only masters, style, and genre. Use the native structure from `references/mechanics.md`; never invent an unsupported top-level key when the request maps to an existing mechanic.

Before delivery, consider all recognised top-level mechanics: `pack`, `private`, `shared`, `masters`, `people`, `categories`, `dials`, `variation`, and `fields`.

Also handle their modifiers and behaviours: category `replace`, master `inherits`, compact master tags `m`, cast tokens `{1}` to `{5}`, `{v}` value substitution, `carryToFollowUp`, `attachTo`, `splitList`, `limit`, `rows`, `default`, category deduplication, and merge precedence.

Time-of-day has two distinct forms:

- selectable weather/time modules belong in the existing `CONDITIONS` category;
- random time changes used by **Vary** belong in a `variation` pool.

Sliders always use `dials`.

## What to create

Translate the user's request into a self-contained DLC bundle. A bundle may contain any native Prompt Bench mechanic. Common files include:

- a new master, e.g. `00-master-<theme>.json`;
- style modules as the normal `STYLE` category, order 22;
- genre modules as the normal `GENRE` category, order 28;
- existing/new category modules such as `CONDITIONS`, `LIGHT`, `POSE`, `PROPS`, or another appropriate category;
- dials/sliders;
- Vary/variation pools;
- free-text fields;
- shared prompt blocks;
- people/cast entries, normally private when they describe real people.

Style and genre are ordinary Prompt Bench categories, not special top-level JSON keys.

If a new master is requested, default its generated style/genre items to that master only. If there is no new master, default them to `"*"` unless the user names target master IDs. Keep new master IDs to one character and avoid collisions.

Do not modify existing Prompt Bench pack files merely to make generated DLC work. Generated DLC should be additive unless the user explicitly requests replacement behaviour.

## Scalable counts

Treat requested counts as exact requirements. If the user asks for 100 styles and 100 genres, create exactly 100 distinct style entries and exactly 100 distinct genre entries.

For large sets, author in batches with a coverage plan. Vary meaningful dimensions such as period, material, production method, line/shape language, palette logic, lighting, composition, narrative conventions, setting, social context, technology, and tone. Do not inflate counts with synonyms or tiny rewrites.

Every module should be a usable positive instruction. Prefer concrete image-making or scene-making cues over vague labels.

## Build workflow

For the master/style/genre shortcut:

1. Create a temporary authoring spec with `scripts/dlc_pack_tool.py init <spec.json>` or write equivalent JSON.
2. Set `theme` and optional `slug`.
3. Add `master` or set it to `null`. Use `"id": "AUTO"` when the repo should determine the next unused master ID.
4. Put style entries under `style.items` and genre entries under `genre.items`, with exact `count` values.
5. Build:

   `python skills/dlc-pack-generator/scripts/dlc_pack_tool.py build <spec.json> <output-dir> --clean`

For every other mechanic, author native JSON directly from `references/mechanics.md`.

Then run **both** validators:

`python skills/dlc-pack-generator/scripts/dlc_pack_tool.py validate <output-dir>`

`python skills/dlc-pack-generator/scripts/validate_mechanics.py <output-dir>`

The first checks general Prompt Bench compatibility and cross-file category duplicates. The strict mechanics validator checks field-level structure for every recognised mechanic, including shared blocks, masters, people, categories, dials, variation pools, fields, and top-level privacy metadata.

The builder automatically splits very large style/genre categories into numbered files to stay below Prompt Bench's 512 KB per-file server limit. Apply the same size rule to manually authored mechanic packs.

## Validation requirements

Do not deliver or upload a bundle unless validation passes. Also inspect the finished content semantically:

- requested counts match exactly;
- no exact duplicate module text exists where Prompt Bench would merge it;
- every master ID and `m` tag targets the intended master(s);
- every requested mechanic follows its field-level structure in `references/mechanics.md`;
- dial stops are ordered and cover the slider range;
- variation pools and fields behave as the user intended;
- files are valid UTF-8 JSON objects using recognised Prompt Bench keys;
- no generated file exceeds 512 KB;
- no unrelated repository file was changed;
- no private cast/person data was copied into a public pack unless explicitly requested.

If validation fails, fix the bundle and rerun validation. Do not deliver a knowingly broken set.

## Ready-to-commit output

The final output directory itself is the ready-to-commit file set. Keep it clean: only Prompt Bench pack JSON files required by the request. Do not add a manifest JSON that the Prompt Bench loader could mistake for a pack.

If the user wants the files added to the main Prompt Bench repo, place only the generated pack files in the requested DLC location and avoid unrelated edits.

## Delivery and upload priority

After generation and validation, deliver the bundle in this order:

1. **Preferred:** if a connected GitHub tool can write to `https://github.com/flyinggoatman/prompt-bench-packs`, upload the generated bundle there without asking for another destination. Use a clear theme/slug folder and preserve the complete generated file set.
2. If that repository is unavailable or not writable, ask where the bundle should be uploaded and suggest suitable destinations that are actually available through connected tools, such as another writable GitHub repository or connected cloud storage.
3. If no suitable connector is connected, explain which compatible connector could perform the upload and let the user choose whether to connect it.
4. If the user does not want to use a connector, create a complete `.zip` containing the validated file set and provide a download link so they can upload it themselves.

Never claim an upload succeeded unless the destination action actually succeeded.

## Completion report

Keep the final report short. State the theme, master ID if created, exact generated counts, mechanic types included, validation result, destination, and the repository location or fallback ZIP.
