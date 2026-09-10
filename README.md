# Prompt Bench

A single HTML file that assembles image prompts from one master prompt plus stackable modules. It runs entirely on your device. Nothing is sent anywhere and it needs no internet connection.

## Running it

Open `prompt-bench.html` in any browser. It works on its own with a full built in set of masters, modules, dials and variation pools.

## Adding your own content

Everything the app knows about lives in JSON pack files. The built in set is duplicated in the `packs` folder so you have a working example of every format.

To add or change anything:

1. Put a `.json` file anywhere inside the `packs` folder, including in subfolders.
2. Open the app and press **Load folder**, then choose the `packs` folder.
3. The app reads every JSON file it finds and merges them.

Loaded packs are saved on the device, so you only need to load again after you add or edit a file. **Load files** picks individual files instead, which is the fallback on phones where folder picking is unavailable. You can also drag files onto the page on a desktop.

A browser cannot read a folder without being handed it, so there is no way to skip that one tap. Nothing else about the workflow needs the HTML file to change.

### Buttons

- **Load folder** reads a whole folder of packs.
- **Load files** reads one or more individual files.
- **Export** writes the merged set as a single JSON file, which is the easiest way to get a copy you can edit by hand.
- **Clear** forgets every loaded pack and returns to the built in set.

## Pack file format

Every pack is one JSON object. Every key is optional, so a file can contain just one thing. Files are merged in name order, and later files win, so prefixing filenames with numbers controls precedence.

```json
{
  "pack": "Name shown in the app",
  "masters": [],
  "shared": [],
  "categories": [],
  "dials": [],
  "variation": [],
  "fields": []
}
```

### masters

One entry per master prompt. A master may declare `"inherits": "B"`, which makes every module tagged for master B also appear under it. The DLC Sequence master uses this so all the Moment scenes are available to it. A module tagged `"m": "*"` appears under every master.

One entry per master prompt. Masters are mutually exclusive in the app. Reusing an existing `id` overwrites that master.

```json
{
  "masters": [
    {
      "id": "D",
      "name": "Diagram",
      "blurb": "Shown under the name in the picker.",
      "body": "ROLE\nThe text placed at the very top of the assembled prompt."
    }
  ]
}
```

### shared

Text blocks inserted into every prompt regardless of master. The built in `core` entry holds the cast, the context, the joke rule, the constraints and the craft notes. Reusing the id `core` replaces it entirely, so to change one paragraph, export first and edit the exported copy.

```json
{
  "shared": [
    { "id": "core", "label": "Core", "blocks": ["FIRST BLOCK", "SECOND BLOCK"] }
  ]
}
```

### people

The cast. Up to five slots, and the app can run with none at all. Matching an existing `id` overwrites that character, so a pack can replace one member without touching the rest.

```json
{
  "people": [
    {
      "id": "p1",
      "name": "Ada",
      "kind": "person",
      "marker": "a battered leather satchel always on her shoulder",
      "looks": "Tall, sixties, close cropped grey hair",
      "wears": "Workwear, boots, layers",
      "manner": "Says very little and misses nothing",
      "likes": "birdwatching, crosswords",
      "avoid": "costumes"
    }
  ]
}
```

- `kind` is `person` or `animal`. An animal is left out of the outfit rule.
- `marker` is the most important field. It is the thing that is always present, and it is what makes a character recognisable when the drawing style has simplified their face.
- `likes` becomes objects in the scene, never a label.
- `avoid` is per character, so one member can ban something without it affecting anyone else.
- Photos are never stored in a pack. They live only on the device that added them.

Shipping `{"people": []}` in a high numbered file gives you an empty cast to start from.

### Name tokens

Module text, dial text, variation options and field wrappers can use `{1}` to `{5}`. Each resolves to the name in that cast slot, or to "somebody" if the slot is empty. This is how the built in scene modules survive a change of cast: write `{1} has stepped on a squeaky floorboard` rather than naming anyone directly.

### categories

A category is a group of modules. Matching an existing `key` adds your items to that category rather than creating a second one, which is how you extend Scene or Palette without touching the original file.

```json
{
  "categories": [
    {
      "key": "SCENE",
      "label": "Scene",
      "note": "Shown next to the group name",
      "order": 30,
      "items": [
        { "m": "AB", "t": "The line of text added to the prompt." }
      ]
    }
  ]
}
```

- `m` lists which master ids the module suits, as one string. `"AB"` means it appears under masters A and B. `"ABC"` means always.
- `order` sets where the category sits in the list and in the assembled prompt. Lower comes first.
- `label`, `note` and `order` can be left out when adding to a category that already exists.
- Add `"replace": true` to a category to wipe its existing items before adding yours.
- Module numbers are assigned automatically after merging, so they shift when you add packs.

### dials

Sliders. Instead of printing a number, each dial emits a sentence based on where it sits. `stops` are checked in order and the first one whose `upTo` is greater than or equal to the value wins. `{v}` in the text is replaced by the number.

```json
{
  "dials": [
    {
      "id": "grain",
      "label": "Paper grain",
      "lo": "Smooth", "hi": "Rough",
      "min": 0, "max": 10, "value": 4,
      "order": 60,
      "carryToFollowUp": false,
      "stops": [
        { "upTo": 3, "text": "Smooth stock, almost no tooth." },
        { "upTo": 10, "text": "Heavy tooth, the paper texture visible through every flat area." }
      ]
    }
  ]
}
```

`carryToFollowUp` includes this dial in Follow-up mode, which otherwise only carries the modules you tick.

### variation

Pools the Vary button draws from. Each pool contributes at most one line, and the app uses the first three pools. Add pools with a low `order` if you want them to be the ones that fire.

```json
{
  "variation": [
    { "id": "weather", "order": 15,
      "options": ["It is raining outside.", "It is far too bright."] }
  ]
}
```

### fields

Free text boxes.

```json
{
  "fields": [
    {
      "id": "notes",
      "label": "Heading above the box",
      "hint": "Smaller explanatory line",
      "placeholder": "Greyed out example text",
      "order": 30,
      "section": "ALSO",
      "wrap": "{v}",
      "carryToFollowUp": true
    }
  ]
}
```

- `section` is the heading the value appears under in the assembled prompt. Boxes sharing a section are grouped.
- `wrap` is a template, with `{v}` replaced by what you typed. Use it to phrase the input, for example `"Also keep out: {v}."`
- `attachTo` puts the value inside a shared block instead of its own section. The built in avoid box uses `"attachTo": "core"`.
- `splitList` splits on commas and newlines, and `limit` caps how many items are used.

## DLC packs

`packs/dlc/` holds the expansion set: a fourth master (Sequence), painting and print media, a Pose category of dynamic bodies, Gag mechanisms, Light, Conditions, Structure, Finish, Shape, five more dials, four more variation pools, two more fields, and extensions to every original category. Delete any file you do not want. Nothing in the core packs depends on them.

When two packs contain a module with identical text, the app keeps one copy and merges the master tags, so a DLC file can widen where an existing module appears without duplicating it.

## Public page and admin page

Served from `server.py`, the main page is public and needs no login. `/admin` is protected by HTTP Basic Auth and is where packs are installed and removed.

A pack containing `"private": true` at the top level is never sent to the public page. The built in cast pack uses this, because it describes real people. On the admin page, press **Load private packs into this browser** once and they are stored in that browser's local storage, so your cast travels with your device rather than with the site. **Forget them again** removes them from that browser.

Uploads accept JSON only, are capped at 512 KB, must contain a recognised pack key, and are written with a sanitised filename into `uploads/`, which is the only writable path. Packs in `packs/` are read only and can only be changed on the server.

## Running it on a server

`server.py` is a read only server with Basic Auth. When the app is served by it, the app fetches `api/packs` on load and merges every JSON file under `packs/` automatically, with no folder picker. Adding a pack becomes: put the file in the folder, reload the page. The `deploy/` folder has a Dockerfile and Compose file, and `DEPLOY.md` is the brief to hand to whoever runs your VPS.

Opened directly from disk the app behaves exactly as before and ignores the server features.

## DLC wave two

`packs/dlc2/` fills out the thin categories: more moods, framing, print finishes, canvas shapes and in image text options, plus a further media set covering animation techniques, street and public art, craft surfaces and deliberately ugly digital media.

## A note on writing modules

Modules work best written as something to do rather than something to avoid. Image models have no true negative field, so a banned word still enters the prompt and can summon the thing it names. The one fixed ban list lives in the shared core block, stated once. Everything else occupies the space positively so the default has nowhere to land.
