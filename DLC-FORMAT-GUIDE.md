# Prompt Bench DLC Format Guide

This is the canonical authoring guide for Prompt Bench JSON packs.

Use this repository as the reference for structure and behaviour. Finished distributable DLC belongs in `flyinggoatman/prompt-bench-packs`.

## The short version

A Prompt Bench pack is one JSON object. It may contain one mechanic or several mechanics together.

```json
{
  "pack": "My Pack",
  "private": false,
  "shared": [],
  "masters": [],
  "people": [],
  "categories": [],
  "wording": {},
  "settings": {},
  "castFields": [],
  "discipline": [],
  "dials": [],
  "variation": [],
  "fields": []
}
```

Only include the keys your pack actually needs.

The app currently consumes **11 payload types**:

| Type | Top-level key | Normal home in this repository | Working example |
| --- | --- | --- | --- |
| Shared prompt blocks | `shared` | `packs/masters/` | `packs/masters/00-shared-core.json` |
| Master prompts | `masters` | `packs/masters/` | `packs/masters/01-masters.json` |
| Cast / characters | `people` | `packs/people/` | `packs/people/00-people.json` |
| Module categories | `categories` | `packs/categories/`, `packs/dlc/`, `packs/dlc2/` | `packs/categories/30-scene.json` |
| App wording | `wording` | `packs/controls/` | `packs/controls/40-wording.json` |
| Global settings | `settings` | `packs/controls/` | `packs/controls/40-wording.json` |
| Cast field definitions | `castFields` | `packs/controls/` | `packs/controls/40-wording.json` |
| Anatomy/continuity rules | `discipline` | `packs/controls/` | `packs/controls/50-discipline.json` |
| Sliders / dials | `dials` | `packs/controls/` | `packs/controls/10-dials.json` |
| Random variation pools | `variation` | `packs/controls/` | `packs/controls/20-variation.json` |
| Free-text controls | `fields` | `packs/controls/` | `packs/controls/30-fields.json` |

There are also two pack-level modifiers:

- `pack`: a human-readable pack name. The Windows installer also uses names beginning `DLC:` and `DLC2:` as routing hints.
- `private`: when `true`, the server does not expose that whole pack on the public page, and shareable prompts leave it out.

## Merge rules

Packs are merged in filename order. A later file can extend or change an earlier file, so numeric prefixes are useful.

Examples:

```text
10-base.json
20-extra.json
90-overrides.json
```

The merge rules are:

- `shared`, `masters`, `people`, `dials`, `variation`, `fields`, and `discipline` merge by `id`.
- `castFields` merges by `key`.
- Matching entries are property-merged. Properties supplied by the later file win. Properties it does not mention remain from the earlier entry.
- `wording` and `settings` merge property by property.
- `categories` merge by category `key` using the special category rules described below.
- `castFields` and `discipline` entries with `"drop": true` are removed after merging.

A pack can contain several top-level types at once. Focused files are usually easier to maintain, but mixed packs are valid.

## 1. Shared prompt blocks: `shared`

Shared blocks are inserted into every full prompt, regardless of which master is selected.

```json
{
  "pack": "Shared Craft Rules",
  "shared": [
    {
      "id": "craft-extra",
      "label": "Extra craft",
      "blocks": [
        "Keep the focal action immediately readable.",
        "Use clear foreground, middle-ground and background separation."
      ]
    }
  ]
}
```

Fields:

- `id`: stable identity used for merging.
- `label`: human-readable name.
- `blocks`: array of prompt text blocks.

If a later pack supplies the same `id`, its supplied properties replace those properties. Supplying a new `blocks` array replaces that whole array for that shared entry.

The built-in shared core is `packs/masters/00-shared-core.json`.

## 2. Master prompts: `masters`

Masters define the overall object or image concept. The user picks one master at a time.

```json
{
  "pack": "Master Example",
  "masters": [
    {
      "id": "E",
      "name": "Field Guide",
      "blurb": "An illustrated reference-page composition.",
      "body": "ROLE\nCreate one illustrated field-guide page with a strong visual hierarchy."
    }
  ]
}
```

Fields:

- `id`: master identifier. The built-ins use single characters such as `A`, `B`, `C`, `D`.
- `name`: name shown in the master picker.
- `blurb`: short description shown under the name.
- `body`: text placed at the start of the assembled prompt.
- `inherits`: optional master id whose compatible modules should also be available.

Example inheritance:

```json
{
  "id": "D",
  "name": "Sequence",
  "inherits": "B",
  "body": "ROLE\nDraw a short sequence..."
}
```

Module compatibility uses string membership, so keeping master ids to one character is safest unless the app logic is deliberately changed.

A module tagged `"m": "*"` is available to every master.

## 3. Cast / characters: `people`

`people` supplies reusable cast slots.

```json
{
  "pack": "Cast Example",
  "people": [
    {
      "id": "p1",
      "name": "Ada",
      "kind": "person",
      "marker": "a battered leather satchel always on her shoulder",
      "looks": "Tall, sixties, close-cropped grey hair",
      "wears": "Workwear, boots, layers",
      "manner": "Says very little and misses nothing",
      "likes": "birdwatching, crosswords",
      "avoid": "costumes"
    }
  ]
}
```

Important fields:

- `id`: stable identity used for merging.
- `name`: displayed name and token source.
- `kind`: normally `person` or `animal`.
- Other keys correspond to active `castFields`. The built-in fields are `marker`, `looks`, `wears`, `manner`, `likes`, and `avoid`.

A later entry with the same `id` only needs to provide the properties it wants to change.

`{"people": []}` is valid and can be used in a high-numbered pack when you want the starting cast to be empty.

Photos are never stored in pack JSON.

### Name tokens

Prompt text can use cast tokens such as `{1}`, `{2}`, and so on. They resolve to the names in those cast slots.

The usable range follows `settings.maxCast`, up to 9.

## 4. Module categories: `categories`

Categories are the stackable modules shown in the Modules section.

```json
{
  "pack": "Scene Extras",
  "categories": [
    {
      "key": "SCENE",
      "label": "Scene",
      "note": "What is actually happening",
      "order": 30,
      "items": [
        {
          "m": "AB",
          "t": "A sudden interruption changes what everybody is doing."
        }
      ]
    }
  ]
}
```

Category fields:

- `key`: stable category identity. Matching an existing key extends that category.
- `label`: user-facing category name.
- `note`: short explanation shown with the category.
- `order`: category order. Lower numbers appear earlier.
- `replace`: optional boolean. When `true`, clears that category's existing items before adding this file's items.
- `items`: module entries.

Module fields:

- `m`: master compatibility string. `"AB"` means masters A and B. `"*"` means all masters.
- `t`: text added to the prompt.

Optional module fields for cast size:

- `needs`: how many characters the module needs. Derived from the highest `{1}`-`{9}` token when it is not declared, so it only has to be written where the requirement is in the prose rather than in a token.
- `alt`: wording for a smaller cast, keyed by size, as `{"1": "...", "2": "..."}`. A module with an alternative for every size below `needs` stays usable at any cast size instead of disappearing.
- `strangers`: `true` where the extra people are unnamed passers-by rather than cast members.
- `castOk`: `true` where a number in the text counts something other than people, such as inks, panels or words, so the audit leaves it alone.

Tokens usable in `t` and in every `alt`:

- `{1}` to `{9}`: a character by position. `{cast}` names all of them.
- `{n}`: the cast size as a digit, for a line of instruction.
- `{N}`: the cast size as a word, for prose. Write "all {N} of them", not "all {n} of them", so a cast of three reads "all three of them" rather than "all 3 of them".
- `{s}`, `{is}`, `{they}`, `{them}`, `{their}`: grammar that follows the cast size.

Never write a cast count as a literal. "All three of them" is right at exactly one cast size and wrong at every other; `{N}` is right at all of them. `.github/audit-cast-requirements.py` fails the build on a literal count, on two alternatives written word for word the same, on an alternative that can never be reached, and on a gap that would hide a module at some size.

If two modules in the same category have identical `t` text, Prompt Bench keeps one copy and combines their master tags.

If `m` is omitted, the current merge code defaults it to `ABC`.

For an expansion wave, the same `categories` format can live under `packs/dlc/` or `packs/dlc2/`. The folder does not change the JSON grammar.

## 5. App wording: `wording`

`wording` overrides the phrases Prompt Bench itself contributes around pack content.

```json
{
  "pack": "Wording Example",
  "wording": {
    "castHeading": "CAST",
    "thisImageHeading": "THIS IMAGE",
    "moduleLine": "{LABEL}: {v}",
    "followUpItem": "- {v}"
  }
}
```

Only include the strings you want to change. Other built-in strings remain in place.

The complete current key set is demonstrated in `packs/controls/40-wording.json` and includes:

```text
castHeading
castWithPhotos
castWithoutPhotos
outfitRule
missingPhotoOne
missingPhotoMany
descriptionOpen
listTwo
listMany
thisImageHeading
moduleLine
dialsHeading
variationHeading
defaultSection
followUpOpen
followUpItem
followUpClose
publicIntro
publicCharacters
publicCastIntro
publicCastWhoPerson
publicCastWhoAnimal
publicCastName
publicCastField
publicCastRepeat
```

Useful wording tokens include `{v}`, `{name}`, `{NAME}`, `{names}`, `{label}`, `{LABEL}`, and cast tokens such as `{1}`.

Unknown tokens are left untouched.

## 6. Global settings: `settings`

Settings change global Prompt Bench behaviour.

```json
{
  "pack": "Settings Example",
  "settings": {
    "maxCast": 7,
    "variationPools": 4
  }
}
```

Current settings:

- `maxCast`: number of cast slots, clamped to 1 through 9.
- `variationPools`: number of variation pools used by Vary. `0` disables variation output.
- `requirePhoto`: whether a named character with no photo makes the prompt stop and ask for one. `true` by default; `false` where the subject is invented from the modules, as on the Persona Bench.
- `defaultMediumHold`: starting value for the reference against medium slider. `0` is the photograph deciding how a face is drawn, `10` is the medium deciding. `8` by default, meaning the medium leads.
- `minQuestions`, `maxQuestions`, `defaultQuestions`: bounds and starting value for the "how many questions" slider. `1`, `8` and `4` by default.
- `styleFirst`: category keys lifted out of the module list and stated before anybody is described, under `HOW THIS IS DRAWN`. Defaults to `["MEDIUM", "FINISH", "PALETTE", "LIGHT"]`. Order is instruction: a style stated after a reference photograph is a style applied to everything except the face.

Settings merge property by property, so a file can change only one setting.

## 7. Cast field definitions: `castFields`

`castFields` controls the per-character input boxes and how each value becomes prompt text.

```json
{
  "pack": "Cast Field Example",
  "castFields": [
    {
      "key": "voice",
      "label": "Voice",
      "hint": "How they sound.",
      "line": "Sounds like {v}.",
      "order": 15,
      "promptOrder": 15
    },
    {
      "key": "manner",
      "drop": true
    }
  ]
}
```

Fields:

- `key`: stable field identity.
- `label`: label shown above the input.
- `hint`: helper text.
- `line`: prompt template. `{v}` is the typed value; `{name}` and `{NAME}` are the character name.
- `order`: position of the input on the page.
- `promptOrder`: position of its sentence in the prompt.
- `outfitRule`: when `true`, identifies the field as clothing for the outfit behaviour.
- `drop`: removes the matching field after merging.

Structural character values such as `name`, `kind`, photo and free written description are not cast fields.

## 8. Anatomy and continuity rules: `discipline`

`discipline` supplies the optional Extra care with anatomy and continuity block.

```json
{
  "pack": "Discipline Example",
  "discipline": [
    {
      "id": "hands",
      "order": 20,
      "text": "Each hand has four fingers and one thumb."
    },
    {
      "id": "face",
      "drop": true
    }
  ]
}
```

Fields:

- `id`: stable rule identity.
- `order`: prompt order.
- `text`: rule wording.
- `drop`: removes that rule after merging.

Write the desired state positively. These rules are intended to describe what the finished image contains rather than naming mistakes to avoid.

## 9. Sliders / dials: `dials`

Dials are sliders whose position emits text rather than a number.

```json
{
  "pack": "Dials Example",
  "dials": [
    {
      "id": "grain",
      "label": "Paper grain",
      "lo": "Smooth",
      "hi": "Rough",
      "min": 0,
      "max": 10,
      "value": 4,
      "order": 60,
      "carryToFollowUp": false,
      "stops": [
        {
          "upTo": 3,
          "text": "Smooth stock, almost no tooth."
        },
        {
          "upTo": 10,
          "text": "Heavy tooth, with visible paper texture."
        }
      ]
    }
  ]
}
```

Fields:

- `id`: stable dial identity.
- `label`: user-facing name.
- `lo`, `hi`: labels at the two ends.
- `min`, `max`: numeric range.
- `value`: default value.
- `order`: UI and prompt order.
- `carryToFollowUp`: include the dial's emitted wording in follow-up mode.
- `stops`: ordered threshold entries.

Prompt Bench checks `stops` in order and uses the first one whose `upTo` is greater than or equal to the current value.

`{v}` inside stop text is replaced with the numeric dial value.

## 10. Random variation pools: `variation`

Variation pools supply optional random lines for the Vary button.

```json
{
  "pack": "Variation Example",
  "variation": [
    {
      "id": "weather",
      "order": 15,
      "options": [
        "It is raining outside.",
        "It is far too bright."
      ]
    }
  ]
}
```

Fields:

- `id`: stable pool identity.
- `order`: pool order.
- `options`: strings the pool can emit.

Each selected pool contributes at most one line. The number of pools used is controlled by `settings.variationPools`.

## 11. Free-text controls: `fields`

Fields create user-editable text inputs outside the per-character cast editor.

```json
{
  "pack": "Fields Example",
  "fields": [
    {
      "id": "notes",
      "label": "Extra notes",
      "hint": "Anything this image specifically needs.",
      "placeholder": "Example text",
      "order": 30,
      "section": "ALSO",
      "wrap": "{v}",
      "carryToFollowUp": true
    }
  ]
}
```

Fields:

- `id`: stable identity.
- `label`: input label.
- `hint`: helper text.
- `placeholder`: empty-state example.
- `order`: input order.
- `section`: assembled-prompt heading. Fields with the same section are grouped.
- `wrap`: output template using `{v}`.
- `carryToFollowUp`: include this field in follow-up mode.
- `attachTo`: place the rendered value inside a shared block instead of its own section.
- `splitList`: split comma/newline input into items.
- `limit`: maximum number of split items used.

If `section` is omitted, `wording.defaultSection` is used.

## Pack-level modifier: `private`

A pack can mark itself private:

```json
{
  "pack": "Private Cast",
  "private": true,
  "people": []
}
```

When served through `server.py`, private packs are not sent to the public page. The shareable-prompt builder also omits the whole pack.

Use this for personal material, not as a substitute for a secrets store. Do not place passwords, API keys or other credentials in Prompt Bench packs.

## Installer routing metadata

`Install Packs.bat` normally infers the target from the JSON structure.

A pack can also give the installer an explicit relative destination using one of these metadata keys:

```json
{
  "pack": "My DLC",
  "installPath": "packs/dlc",
  "categories": []
}
```

Recognised installer aliases are:

```text
installPath
install_path
targetPath
target_path
destination
target
```

These are installer metadata only. Prompt Bench itself ignores unknown top-level keys.

The installer refuses an explicit destination that escapes the local `packs` tree.

## Recommended folders

The main repository currently uses:

```text
packs/
  masters/      shared blocks and core masters
  people/       cast packs
  categories/   core module categories
  controls/     wording, settings, castFields, discipline, dials, variation, fields
  dlc/          first expansion wave
  dlc2/         second expansion wave
```

A DLC expansion can mix several mechanics in `dlc/` or `dlc2/`. The folder is organisational; the JSON keys control the actual behaviour.

For loose files installed by `Install Packs.bat`:

- a `pack` beginning `DLC:` routes to `packs/dlc/`;
- a `pack` beginning `DLC2:` routes to `packs/dlc2/`;
- `masters` or `shared` route to `packs/masters/`;
- `people` route to `packs/people/`;
- `wording`, `settings`, `castFields`, `discipline`, `dials`, `variation`, and `fields` route to `packs/controls/`;
- ordinary `categories` route to `packs/categories/`.

Use explicit `installPath` when a mixed pack needs a destination that cannot be inferred unambiguously.

## ZIP pack layout

The installer accepts `.zip` as well as loose JSON.

The cleanest ZIP contains a top-level `packs/` folder:

```text
My-DLC.zip
  packs/
    dlc/
      20-my-medium.json
    controls/
      70-my-dial.json
```

That `packs/` tree is merged into the Prompt Bench `packs/` tree.

A ZIP may instead contain known folder names such as `masters`, `controls`, `categories`, `people`, `dlc`, or `dlc2`; matching folder contents are merged into the same-named Prompt Bench folder.

Loose JSON inside a ZIP is inspected individually and routed using the same rules as loose JSON outside a ZIP.

## Compatibility and authoring rules

### Keep JSON strict

Use standard JSON:

- double quotes around keys and strings;
- no comments;
- no trailing commas;
- valid UTF-8.

### Prefer stable ids

Any type that merges by `id` or `key` should keep that identifier stable between releases. Changing it usually creates a second entry instead of updating the first.

### Use numeric filename prefixes for ordering

If one file depends on another being merged first, make the order explicit:

```text
20-base-dials.json
21-extra-dials.json
```

### Write modules positively

Image-generation modules generally work better when they describe the desired result instead of repeating unwanted concepts.

### A file does not need every key

All of these are valid packs:

```json
{ "pack": "One Dial", "dials": [] }
```

```json
{ "pack": "One Master", "masters": [] }
```

```json
{ "pack": "Mixed Expansion", "masters": [], "categories": [], "dials": [] }
```

## Before publishing a DLC pack

Check all of these:

1. The file parses as JSON.
2. It contains at least one of the 11 supported payload keys.
3. Stable entries have stable `id` or `key` values.
4. Master tags in category items point at real master ids, or use `*` intentionally.
5. Filename order is deliberate where overrides matter.
6. No private personal information is included unless the pack is intentionally private and stays in the private repository.
7. No credentials or secrets are included at all.
8. Loose installer routing is unambiguous, or the file supplies `installPath`.
9. The pack is tested by loading it into Prompt Bench and assembling at least one prompt that exercises its new mechanic.
10. Finished distributable DLC is placed in `flyinggoatman/prompt-bench-packs`; this private repository remains the authoritative implementation and format reference.

## Source of truth

When documentation and behaviour ever disagree, inspect `modelFrom()` in `prompt-bench.html`. It contains the actual merge contract for the supported pack keys. Update this guide whenever that contract changes.
