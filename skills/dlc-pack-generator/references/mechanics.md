# Prompt Bench complete importable mechanics

This is the skill's structural handbook for authoring Prompt Bench JSON packs. The live repository remains the source of truth. If runtime code or README rules change, follow the live repository and update this reference.

## 1. Pack envelope

Every importable file is one UTF-8 JSON object. A file may contain any combination of the recognised keys below.

```json
{
  "pack": "Human-readable pack name",
  "private": false,
  "shared": [],
  "masters": [],
  "people": [],
  "categories": [],
  "dials": [],
  "variation": [],
  "fields": []
}
```

Recognised top-level keys are exactly:

`pack`, `private`, `shared`, `masters`, `people`, `categories`, `dials`, `variation`, `fields`.

Rules:

- `pack` is the display name. It is not a unique identifier.
- `private: true` keeps a server-side pack out of the public `/api/packs` response. Use it for real-person/cast information or other content that should not be publicly served.
- A server upload must be a JSON object, contain at least one recognised key, and be no larger than 512 KB per file.
- Files merge in filename/path order. Numeric filename prefixes are therefore useful for deterministic precedence.
- Do not invent new top-level mechanics. New visual concepts normally belong in `categories`.

## 2. Shared prompt blocks

Use `shared` for text that should be inserted into every full prompt regardless of the chosen master.

```json
{
  "pack": "Shared rules",
  "shared": [
    {
      "id": "craft",
      "label": "Craft rules",
      "blocks": [
        "CRAFT\nKeep the line work visibly handmade.",
        "CONSISTENCY\nKeep recurring character markers stable."
      ]
    }
  ]
}
```

Structure:

- `id`: required stable identifier used for merging and by `fields.attachTo`.
- `label`: descriptive UI/reference label.
- `blocks`: ordered array of prompt strings.

Merge rule: shared entries merge by `id`; a later entry with the same `id` replaces the earlier shared entry completely. The built-in shared core uses `id: "core"`.

## 3. Masters

Masters are mutually exclusive base prompt modes.

```json
{
  "pack": "DLC: Storyboard master",
  "masters": [
    {
      "id": "E",
      "name": "Storyboard",
      "blurb": "A sequence-minded scene with continuity between beats.",
      "inherits": "B",
      "body": "ROLE\nCreate one storyboard-like moment.\n\nSTRUCTURE\nKeep the event readable at a glance."
    }
  ]
}
```

Structure:

- `id`: required. Keep it to one non-whitespace character because category suitability uses the compact `m` string.
- `name`: required picker name.
- `blurb`: optional short explanation under the picker.
- `body`: required base prompt text.
- `inherits`: optional single master ID. If master `E` inherits `B`, category items tagged for `B` also appear for `E`.

Merge rule: masters merge by `id`; later same-ID masters replace earlier ones.

## 4. People / cast entries

Use `people` for reusable cast slots. Prompt Bench supports up to five active cast slots and resolves `{1}` through `{5}` against them.

```json
{
  "pack": "Fictional cast",
  "private": true,
  "people": [
    {
      "id": "p1",
      "name": "Ada",
      "kind": "person",
      "marker": "a battered leather satchel always on her shoulder",
      "looks": "Tall, sixties, close-cropped grey hair",
      "wears": "Workwear, boots and layered shirts",
      "manner": "Quiet, observant and deliberate",
      "likes": "birdwatching, maps, crosswords",
      "avoid": "formal evening wear"
    }
  ]
}
```

Structure:

- `id`: stable merge identifier, normally `p1` to `p5`.
- `name`: displayed and substituted into `{1}` to `{5}` tokens.
- `kind`: `person` or `animal`. Animals are omitted from the outfit rule.
- `marker`: strongest persistent recognition/signifier detail.
- `looks`: physical appearance.
- `wears`: ordinary clothing guidance; may be blank for animals.
- `manner`: behaviour/body-language guidance.
- `likes`: interests converted into scene evidence/objects, not labels.
- `avoid`: per-character exclusions.

Merge rule: people merge by `id`; later same-ID entries replace earlier ones. Do not expose real-person data in a public DLC.

## 5. Categories: the selectable module mechanic

Most Prompt Bench DLC content is a category. A category produces a group of tickable prompt modules.

```json
{
  "pack": "DLC: Conditions",
  "categories": [
    {
      "key": "CONDITIONS",
      "label": "Conditions",
      "note": "Weather and time",
      "order": 64,
      "items": [
        { "m": "ABD", "t": "Early morning, long cool shadows and half-finished breakfast." },
        { "m": "*", "t": "Late night, most of the building dark except for one practical lamp." }
      ]
    }
  ]
}
```

Category structure:

- `key`: required stable category identifier. Matching keys merge into one category.
- `label`: visible category name. When supplied later, it updates the existing label.
- `note`: short visible explanation. When supplied later, it updates the existing note.
- `order`: numeric UI/prompt order. Lower appears earlier. Missing order defaults to 999 for a new category.
- `replace`: optional boolean. `true` clears all existing items in that category before adding the incoming items. Use only when replacement is explicitly intended.
- `items`: array of module objects.

Category item structure:

- `m`: compact master-suitability string. `"AB"` means masters A and B. `"*"` means every master. If omitted by the runtime it defaults to `"ABC"`, but generated DLC should normally set it explicitly.
- `t`: prompt instruction text.

Deduplication rule: within a category, exact duplicate `t` text is stored once and its master tags are merged. Exact duplicates can therefore silently reduce an intended variation count.

### Existing category vocabulary

These are the current native category families in the repository. Extend an existing key instead of creating a near-duplicate category when the concept belongs here.

| Key | Order | Purpose |
| --- | ---: | --- |
| `SHAPE` | 5 | Canvas proportion / image shape |
| `FORMAT` | 10 | What kind of designed object/image it is |
| `MEDIUM` | 20 | Physical or simulated art-making medium |
| `FINISH` | 25 | Print/surface finishing and wear |
| `SCENE` | 30 | What is actually happening |
| `POSE` | 35 | What bodies are doing |
| `MOOD` | 40 | Emotional atmosphere |
| `GAG` | 45 | Comedy mechanism |
| `FRAMING` | 50 | Viewer/camera placement |
| `STRUCTURE` | 52 | How the frame/composition is organised |
| `PALETTE` | 60 | Concrete colour choices |
| `LIGHT` | 62 | Lighting source/direction/quality |
| `CONDITIONS` | 64 | Weather, season and time of day |
| `PROPS` | 70 | Specific objects/evidence in the scene |
| `TEXT` | 80 | Words/signage/lettering inside the image |

The DLC generator also uses two additive category conventions when requested:

- `STYLE`, order 22: broad visual treatment and art direction.
- `GENRE`, order 28: narrative/thematic genre conventions.

These are normal categories, not special top-level keys.

### Time of day: selectable vs random

Prompt Bench has two valid ways to express time of day, depending on the requested behaviour.

For a user-selectable module, extend `CONDITIONS`:

```json
{
  "pack": "DLC: More times of day",
  "categories": [
    {
      "key": "CONDITIONS",
      "label": "Conditions",
      "note": "Weather and time",
      "order": 64,
      "items": [
        { "m": "*", "t": "Blue hour just before sunrise, cool ambient light and practical lamps still on." },
        { "m": "*", "t": "High noon, short hard shadows and nowhere for soft light to hide." }
      ]
    }
  ]
}
```

For a random option used by the **Vary** button, use a `variation` pool such as `id: "time"` instead. Do not confuse the two mechanics.

## 6. Dials / sliders

Use `dials` when the user should control an integer slider and different value ranges should emit different prompt text.

```json
{
  "pack": "DLC: Lighting control",
  "dials": [
    {
      "id": "shadow_depth",
      "label": "Shadow depth",
      "lo": "Open",
      "hi": "Crushed",
      "min": 0,
      "max": 10,
      "value": 4,
      "order": 63,
      "carryToFollowUp": false,
      "stops": [
        { "upTo": 3, "text": "Keep shadows open with visible detail." },
        { "upTo": 7, "text": "Use firm shadows with clear separation from lit areas." },
        { "upTo": 10, "text": "Use very deep shadows, preserving only the most important silhouettes. Strength {v}." }
      ]
    }
  ]
}
```

Structure:

- `id`: required stable merge identifier.
- `label`: slider label.
- `lo`: left endpoint label. If omitted, the numeric minimum is shown.
- `hi`: right endpoint label. If omitted, the numeric maximum is shown.
- `min`: integer minimum; runtime default is 0.
- `max`: integer maximum; runtime default is 10.
- `value`: initial slider value; runtime default is `min`.
- `order`: numeric display/prompt order.
- `carryToFollowUp`: optional boolean. If true, this dial's emitted text is included in Follow-up mode.
- `stops`: ordered array of `{upTo, text}` objects.

Stop behaviour:

- Stops are checked in array order.
- The first stop where current value `<= upTo` wins.
- `{v}` inside stop text becomes the current numeric slider value.
- `{1}` to `{5}` may also be used and are resolved after the dial text is selected.
- Put stops in ascending `upTo` order and normally cover the full `max` value.

Merge rule: dials merge by `id`; a later same-ID dial replaces the earlier dial completely.

## 7. Variation pools / Vary button

Use `variation` for randomised prompt nudges. The Vary button chooses at most three pools, then one option from each chosen pool.

```json
{
  "pack": "DLC: Time variation",
  "variation": [
    {
      "id": "time",
      "order": 20,
      "options": [
        "Set it before sunrise.",
        "Set it in flat midday light.",
        "Set it at blue hour.",
        "Set it late at night."
      ]
    }
  ]
}
```

Structure:

- `id`: stable merge identifier.
- `order`: controls ordering of the selected variation sentences after pools have been chosen.
- `options`: array of possible prompt strings. Name tokens `{1}` to `{5}` are allowed.

Behaviour:

- Prompt Bench copies the pools, randomly chooses up to three different pools, sorts those chosen pools by `order`, then picks one option from each.
- More than three pools may exist, but only three contribute on a single Vary result.
- A later pool with the same `id` replaces the earlier pool completely.

Use variation when the choice should be automatic/random. Use a category when the user should deliberately tick a specific option.

## 8. Free-text fields

Use `fields` when the user should type custom text that is transformed into the assembled prompt.

### Standard section field

```json
{
  "pack": "DLC: Notes field",
  "fields": [
    {
      "id": "director_notes",
      "label": "Director notes",
      "hint": "Anything specific this image must include.",
      "placeholder": "For example: the red umbrella is left by the door",
      "default": "",
      "order": 30,
      "section": "ALSO",
      "wrap": "Additional direction: {v}",
      "rows": 4,
      "carryToFollowUp": true
    }
  ]
}
```

### Field attached to a shared block

```json
{
  "pack": "DLC: Extra exclusions",
  "fields": [
    {
      "id": "avoid_extra",
      "label": "Things to keep out",
      "order": 40,
      "attachTo": "core",
      "splitList": true,
      "limit": 3,
      "wrap": "Also keep out: {v}."
    }
  ]
}
```

Field structure:

- `id`: required stable merge identifier.
- `label`: heading above the text box.
- `hint`: optional explanatory text.
- `placeholder`: optional empty-box example.
- `default`: optional initial value.
- `order`: numeric UI/prompt order.
- `rows`: optional textarea row count.
- `section`: prompt heading used for the field's output. If omitted, non-attached fields default to `ALSO`.
- `wrap`: string template containing `{v}`. If omitted, runtime behaves as `{v}`.
- `attachTo`: shared-block `id`. When present, output is inserted after that shared block instead of under its own section.
- `splitList`: optional boolean. When true, input is split on commas and newlines, whitespace is trimmed, and empty entries are discarded.
- `limit`: optional maximum number of items retained after `splitList` processing.
- `carryToFollowUp`: optional boolean. When true, the transformed field value is included in Follow-up mode.

Special `CONTEXT` behaviour: a field whose `section` equals `"CONTEXT"` is emitted directly after the master body under a `CONTEXT` heading and before cast/shared blocks. Avoid creating multiple competing CONTEXT fields unless replacement is deliberate.

Merge rule: fields merge by `id`; later same-ID fields replace earlier ones completely.

## 9. Tokens

### Cast/name tokens

`{1}`, `{2}`, `{3}`, `{4}`, `{5}` resolve to the corresponding active cast slot name. If a slot is empty, the runtime substitutes `somebody`.

Cast tokens work in category item text, dial stop text, variation options, shared blocks, master text and field wrappers where the runtime passes the text through its token filler.

### Value token

`{v}` is mechanic-specific:

- in a dial stop, `{v}` becomes the numeric slider value;
- in a field `wrap`, `{v}` becomes the user's processed field text.

Do not use `{v}` expecting it to mean the same thing outside those contexts.

## 10. Merge and replacement rules

Prompt Bench starts with its built-in model, then merges server packs, then locally loaded packs.

- `shared`, `masters`, `people`, `dials`, `variation`, and `fields` merge by `id`. Later same-ID entries replace earlier entries.
- `categories` merge by `key`.
- A later category may update `label`, `note`, or `order` without replacing existing items.
- `replace: true` clears that category's existing item list before adding incoming items.
- Exact duplicate category item text (`t`) is deduplicated and master tags are combined.
- Category/module numbering is assigned after merging, so hard-coded module numbers are not stable API identifiers.

## 11. Follow-up mode

Follow-up mode intentionally carries only:

- currently selected category modules;
- dials with `carryToFollowUp: true`;
- fields with `carryToFollowUp: true`.

It does not re-emit the entire full prompt. Mark carry behaviour explicitly when a newly created control must survive into follow-up editing.

## 12. Complete mechanic selection guide

Choose the structure by desired user interaction:

| User needs | Mechanic |
| --- | --- |
| Fundamental mutually exclusive prompt mode | `masters` |
| Text always present in full prompts | `shared` |
| Reusable cast/person/animal definition | `people` |
| Tickable visual/scene option | `categories` |
| Time-of-day/weather option the user chooses | `CONDITIONS` category |
| Integer slider such as energy, warmth, clutter | `dials` |
| Automatic random nudge from Vary | `variation` |
| Automatic random time-of-day nudge | `variation` pool with e.g. `id: "time"` |
| User-entered custom prose/list | `fields` |
| Private server-side content | top-level `private: true` |
| Extend an existing category | same category `key` |
| Intentionally wipe/reseed one category | category `replace: true` |
| Reuse another master's modules | master `inherits` |

When a request combines mechanics, one JSON pack may contain several top-level arrays, or the skill may split them into clearly named files for maintainability and the 512 KB upload ceiling.
