---
name: dlc-pack-generator
description: Generate, validate, package, and deliver Prompt Bench DLC masters plus scalable style and genre packs in the repository's native JSON format.
---

# Prompt Bench DLC Pack Generator

Use this skill when a user asks for a new Prompt Bench DLC, expansion, master, style pack, genre pack, or a large themed set of prompt variations.

## Source of truth

Before authoring, inspect the current Prompt Bench repository when repository access is available. At minimum read:

- `README.md`, especially **Pack file format**, **DLC packs**, and **A note on writing modules**.
- `packs/dlc/00-master-sequence.json` for a master example.
- representative category DLC such as `packs/dlc/20-medium-painting.json` and `packs/dlc/30-scene-more.json`.
- the current loader/validation code in `prompt-bench.html` and `server.py` when compatibility rules may have changed.

Do not assume this reference file outranks the live repository. See `references/pack-format.md` for the current compact rules.

## What to create

Translate the user's request into a self-contained DLC bundle. A bundle may contain any combination of:

- a new master, in `00-master-<theme>.json`;
- a style category pack, in `20-style-<theme>.json`;
- a genre category pack, in `30-genre-<theme>.json`.

Style and genre are ordinary Prompt Bench categories, not new top-level JSON keys. Use category key `STYLE`, label `Style`, order `22`; and category key `GENRE`, label `Genre`, order `28`, unless the current repository defines a newer convention.

If a new master is requested, default style and genre items to that master only. If there is no new master, default them to `"*"` unless the user names specific master IDs. Keep new master IDs to one character. Prefer the first unused ID after the repository's existing IDs.

Do not modify existing Prompt Bench pack files merely to make a generated DLC work. Generated DLC should be additive unless the user explicitly requests replacement behaviour.

## Scalable counts

Treat requested counts as exact requirements. If the user asks for 100 styles and 100 genres, create exactly 100 distinct style entries and exactly 100 distinct genre entries.

For large sets, author in batches while maintaining a coverage plan so the final list is genuinely varied. Vary dimensions such as period, material, production method, line/shape language, palette logic, lighting, composition, narrative conventions, setting, social context, technology, and tone where appropriate. Do not inflate counts with synonyms or tiny sentence rewrites.

Every module should be a usable positive instruction. Prefer concrete image-making or scene-making cues over labels such as "very retro" or "more fantasy".

## Build workflow

1. Create a temporary authoring spec using `scripts/dlc_pack_tool.py init <spec.json>` or write the equivalent JSON yourself.
2. Set `theme` and, if useful, `slug`.
3. Add `master` or set it to `null`. Use `"id": "AUTO"` when a new master ID should be selected from the current repo.
4. Put authored style entries under `style.items` and genre entries under `genre.items`. Set each block's `count` to the exact user-requested total.
5. Build with:

   `python skills/dlc-pack-generator/scripts/dlc_pack_tool.py build <spec.json> <output-dir> --clean`

6. Validate the finished output again with:

   `python skills/dlc-pack-generator/scripts/dlc_pack_tool.py validate <output-dir>`

The builder automatically splits very large style/genre categories into numbered files when necessary to stay below Prompt Bench's 512 KB per-file server limit.

## Validation requirements

Do not deliver or upload a bundle unless validation passes. Also inspect the finished content semantically:

- requested counts match exactly;
- no exact duplicate module text exists within the generated category;
- every master ID is compatible with Prompt Bench's compact `m` tags;
- generated modules target the intended master(s);
- files are valid UTF-8 JSON objects using recognised Prompt Bench keys;
- no generated file exceeds 512 KB;
- no unrelated repository file was changed;
- no private cast/person data was copied into a public pack unless the user explicitly requested it.

If validation fails, fix the bundle and rerun validation. Do not hand the user a knowingly broken set.

## Ready-to-commit output

The final output directory itself is the ready-to-commit file set. Keep it clean: only the Prompt Bench pack JSON files required by the request. Do not add a manifest JSON that the Prompt Bench loader could mistake for a pack.

If the user wants the files added to the main Prompt Bench repo, place only the generated pack files in the requested DLC location and avoid unrelated edits.

## Delivery and upload priority

After generation and validation, deliver the bundle in this order:

1. **Preferred:** if a connected GitHub tool can write to `https://github.com/flyinggoatman/prompt-bench-packs`, upload the generated bundle there without asking for another destination. Use a clear folder named from the theme/slug and preserve the complete generated file set.
2. If that repository is unavailable or not writable, ask the user where the bundle should be uploaded and suggest suitable destinations that are actually available through their connected tools, such as another writable GitHub repository or connected cloud storage.
3. If no suitable connector is currently connected, explain which compatible connector could perform the upload and let the user choose whether to connect it.
4. If the user does not want to use a connector, create a complete `.zip` containing the validated file set and provide the download link so they can upload it themselves.

Never claim an upload succeeded unless the destination action actually succeeded.

## Completion report

Keep the final report short. State the theme, master ID if created, exact style/genre counts, validation result, destination, and the files or repository location. If a fallback ZIP was used, link the ZIP directly.
