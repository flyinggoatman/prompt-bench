# Prompt Bench

A single HTML file that assembles image prompts from one master prompt plus stackable modules. It runs entirely on your device. Nothing is sent anywhere and it needs no internet connection.

## Running it

Open `prompt-bench.html` in any browser. It works on its own with a full built in set of masters, modules, dials and variation pools.

The page follows your system light or dark setting. The button in the top bar overrides that for the browser you are using and the choice is remembered. On a wide screen the assembled prompt sits in a panel beside the controls and stays in view while you work; on a phone it sits at the end of the page with Assemble, Copy and Vary pinned to the bottom of the screen.

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
- **Clear** forgets the packs you loaded on this page and returns to the built in set. Private packs pulled in from the admin page are kept, because they usually carry your cast and the admin page is where they are removed.

## How many people are in the picture

The cast counter decides how many characters the prompt is about, and the prompt
now says so plainly: "This image has exactly one character: Mara. The cast
described below is the complete list." That one sentence is what stops a model
asking who Person_2, Person_3 and Person_4 are when you chose one.

Two tick boxes under the counter decide the rest.

- **Other people may appear** lets unnamed background figures into the picture:
  a queue, people at other tables. The prompt describes them as strangers who
  are never named and never become characters. With it off, everybody visible
  belongs to your cast, and modules that need strangers are put away.
- **Ask about more characters** invites whoever runs the prompt to add somebody.
  With it off, which is the default, the prompt states your cast is the whole
  cast and the shareable form ends where your cast ends.

Modules follow the same rule. A module that needs three characters is offered
only when there are three, and the Modules card says how many are being held
back rather than letting them quietly disappear. A pack can say so outright with
`"needs": 2`, or the app works it out from the character tokens in the wording.
A module can also carry `"alt": { "1": "..." }`, wording for a smaller cast, and
it stays available instead of disappearing. `"strangers": true` marks a module
whose extra people are passers by rather than cast.

Reference photos are stated the same way: how many are attached, who each is of,
and that the attached set is the complete one, so other images already in the
conversation are not quietly adopted as references.

## Layouts

The same page arranges itself five ways, chosen from the top bar and remembered
on this device.

- **Classic** is the page as it has always been: one column of cards, the result
  beside it.
- **Workbench** puts a rail beside one section at a time, with the result
  docked. On a phone the rail becomes a scrolling strip.
- **Composer** makes the prompt the wide column and rebuilds it as you work, so
  what you are reading is never out of date.
- **Library** gives the modules the whole page as a grid of cards, every group
  open.
- **Guided** walks the same sections as steps, with Back, Skip and Next.

A layout decides what is on screen and where, never what exists. Every control
is reachable in all five, and switching back loses nothing.

## Reference against medium

A slider in the prompt options, running left to right from **Reference
governs** to **Medium absolute**, deciding how far an attached photograph is
allowed to say how a face is drawn rather than only who it is. Pushing it
right gets you more of the drawing. It sits with the style, inside
`HOW THIS IS DRAWN`, and it starts at Medium leads.

It is a slider rather than a switch because the honest answer sits on a line.
A likeness taken entirely from the photograph gives the pasted-in face, a
face rendered to a standard nothing else in the picture is held to. A likeness
taken entirely from the medium gives somebody who is not quite them. The
useful settings are in between, and which one is right depends on the medium:
a heavy woodcut can carry almost nothing from a photograph, a soft gouache
can carry a good deal.

With no photo attached to any slot there is nothing to trade against, so the
prompt says the medium decides everything and the slider says so too. Attach
a photo and it starts to matter.

## Questions before drawing

**Ask me questions before drawing** puts an instruction at the top of every
prompt, ahead of the role and the style, to interview you first using the
platform's own tick boxes and choice buttons where it has them. **How many
questions** is a slider, one to eight, four by default, and the number goes
into the prompt as a figure to hit rather than a ceiling: ask this many, ask
them all in one interaction, prefer asking to assuming, and do not ask fewer.

Turned off, the prompt says the opposite just as plainly: ask nothing, offer
no questionnaire, decide anything the brief leaves open, and draw in the first
reply. There is no middle setting on purpose. A model told to ask "if anything
is unclear" asks one polite question and guesses the rest, which is the
behaviour the switch exists to replace.

It applies to all three modes, the prompt, the follow-up and the shareable
link, and travels in a saved setup and in a shared link. A setup saved before
the control existed loads as asking, since that is what it was built with.
Packs can move the bounds with `minQuestions`, `maxQuestions` and
`defaultQuestions`.

## Style before people

The prompt states how the picture is made before it describes anybody in it.
The style modules, Medium, Finish, Palette and Light, are lifted out of the
module list into a `HOW THIS IS DRAWN` section near the top, followed by the
standing rules, and only then the cast.

Order is instruction. A receiving AI that meets "reference photograph
attached" before it has been told the style settles the face photographically
and then draws a stylised room around it, which is how you end up with a
photograph of somebody sitting in an illustration. Told the style first, the
face is one more thing drawn that way.

The cast wording backs it up: the photograph is stated to be for identity
only, never for rendering, and a half photographic face in a drawn scene is
called wrong even where the likeness is good. Which categories go first is a
setting, `"settings": { "styleFirst": ["MEDIUM", "FINISH", "PALETTE", "LIGHT"] }`,
so a pack that names its style categories differently can say so.

## Signing in, and the private cast

The cast of real people lives in a pack marked `"private": true`. The server
never serves a private pack to somebody who is not signed in, and the
publishing workflow strips private material out of the public build entirely,
so neither the pack nor the cast in it can reach the public site.

Signing in once is enough. The admin page asks for the password; on a correct
answer the server issues a session cookie, valid for twelve hours, `HttpOnly`
and `SameSite=Strict`. The bench page then asks for packs with `?all=auto`,
which means "whatever this visitor is entitled to": signed in, that includes
the private packs and the cast in them; not signed in, it is exactly the
public list. A visitor is never challenged by the page they came to use, so no
password box appears for anybody but the owner, and the admin page still asks
outright because there the box is the point.

Sessions are held in memory, so restarting the server signs you out and the
admin page asks again. If the cast slots are empty when you arrive, the
likeliest reason is that you have not signed in on the admin page since the
last restart.

A cast nobody has touched is filled in from the packs automatically. Once any
slot has a name, a photo or a description, the packs leave it alone and say so
rather than overwriting somebody's work.

## The Persona Bench

`persona-bench.html` is a second bench for portraits, avatars and personas
rather than scenes, linked from the top bar of each page. It is the same
application underneath, so everything above applies to it, and it has its own
packs, its own masters, its own dials and its own storage.

Its packs live in `packs/persona-packs/`, one folder per category: kind, face,
eyes, skin, hair, facial hair, build, clothing, accessories, signature object,
companion, mount, crop, expression, setting and conditions. Its dials cover the
things a portrait needs and a scene does not, from skin age and skin
imperfections to beard length, likeness against caricature, background presence
and depth of field.

The persona bench does not ask for a photograph. On the main bench a named
character with no photo makes the prompt stop and ask for one, because the cast
are real people being reproduced. A persona is invented from the modules, so
there is nothing to reference: the prompt says so plainly and tells the
receiving AI to build the face from the description rather than asking. A pack
controls this with `"settings": { "requirePhoto": false }`. Photographs still
work on the persona bench if you attach one; they are simply not expected.

The shareable prompt follows the same setting. Where a photograph is expected
it offers the receiving AI an image upload control, tells it what to do with
images that arrive later, and asks it to say who an attached photo is of.
Where one is not, all three clauses are left out, so a persona prompt pasted
into ChatGPT never opens by asking for a picture. The clauses are ordinary
wording keys, `publicUploadOffer`, `publicLaterImages` and `publicPhotoOwner`,
so a pack can reword them rather than restating the paragraphs that hold
them.

The two benches keep out of each other's way. The main bench ignores
`persona-packs/` entirely. The persona bench borrows the categories that decide
how a picture is made, Medium, Finish, Palette, Light, Shape, Format and
Structure, and leaves behind the ones that decide what is happening in it. A
pack can override that by declaring `"bench": "main"`, `"persona"` or `"both"`.

Each bench has its own admin page: `admin.html` for the main packs,
`admin-persona.html` for persona packs, both behind the same password. A GitHub
import from the persona admin page takes the `persona-packs` folder of the
repository and nothing else.

## Two people at once

The bench is safe to leave open in more than one place. What you choose lives in
your own browser, so nobody else's session can move it, and the packs live on
the server, where only the admin pages write.

Those writes are stamped. An admin page sends back the stamp it was shown, and a
write against a stale one is refused with an explanation rather than quietly
overwriting somebody else's install. Reload the page and the write goes through.

An open bench notices too. When you come back to the tab, it checks whether the
server's packs have changed since it loaded, and if they have it says so and
offers a **Reload packs** button. Nothing on your screen moves until you press
it: your selection, your cast and your text are yours.

## Using it from an agent or a script

Everything the page can do, software can do without one: read what is
installed, choose from it, and assemble. See
[agent-interface.md](agent-interface.md) for the command line, the server
routes and the link format. It is the same engine either way, lifted out of the
page by the build, so the two cannot drift apart.

## Working with a large module set

With the DLC packs installed there are several hundred modules, so the Modules section has a few ways to keep them manageable.

- **Search** filters every module as you type, across all groups at once. Groups holding a match open automatically, the matched words are highlighted, and typing a number goes straight to that module. Press `/` anywhere on the page to jump to the box, and Escape to clear it.
- **Expand all** opens or closes every group in one go. Groups you open by hand now stay open when you change master.
- The chips under the search box show everything currently ticked, wherever it sits in the list, so you can see your selection without opening each group. Press the cross on a chip to untick that module, or **Clear all** to start again.
- When many packs are installed, the pack list shows the first few with a **Show more** button rather than filling the screen.

## Sharing a prompt with somebody else

**Copy shareable**, at the top of the Result panel, builds a version of the current prompt that anybody can paste into another AI, and copies it.

It carries the master prompt, the shared craft rules, the modules you ticked, the dials and the variation. It does not carry your cast, your photos or anything you typed into the text boxes.

It also leaves out every pack marked `"private": true`, whole. The server already refuses to serve those and the publishing workflow already strips them, so the shareable prompt honours the same flag: it is built from a model with those packs missing rather than from the merged one, and a name written into a private pack's master, module, dial, wording or cast field hint cannot reach it. Where a private pack had overridden something, the shareable version falls back to the public wording underneath. If the master you have chosen exists only in a private pack it says so instead of building a prompt, and the status line tells you how many packs were held back.

Your cast is replaced by a blank form. Each character becomes `Person_1`, `Person_2` and so on, with every detail shown as a square bracket placeholder to replace:

```
Person_1 is a person.
Name: [optional. Leave this out and I will keep calling them Person_1.]
Signifier: [The one thing always present. This is what makes them recognisable, not their face.]
Appearance: [Build, hair, age, how they carry themselves.]
```

The form keeps the shape your modules refer to and none of who anyone is: exactly one block per cast slot you were using, and nothing else. If you were working with no cast at all, the form stays empty too, and simply invites whoever runs it to add their first character. Whoever runs it can fill the brackets in directly or leave them alone and be asked, and the prompt tells the receiving AI to treat anything still in brackets as unanswered rather than as a description to draw.

The blocks are built from your `castFields`, so a pack that adds a box adds a line here too. A character marked as an animal gets no clothing line, and the prompt says plainly that `Person_2` may be a dog, a cat or a horse, so the same prompt works whoever or whatever is in the picture. Wherever a module uses a name token such as `{1}`, the shareable version writes `Person_1` instead of a name.

The receiving AI is told to ask for whatever is still missing using that platform's native questionnaire or input controls where it has them, and ordinary conversation where it does not.

It is also told to use the conversation it is already in. Where the person has already said something that answers a question, it fills that in rather than asking again, and where a creative choice is nobody's but its own, it makes it. Facts about people are treated more carefully: it fills in what the conversation supports, shows the person the filled in details in one short list, and asks once whether it has them right, offering a way to confirm and a way to say something is wrong. A yes carries on and shapes what it asks next. A no is followed up in ordinary conversation in the same thread, changing only the part that was wrong and keeping the rest. Anything nobody has supplied and the conversation does not support stays a question or stays a placeholder rather than becoming an invention.

Follow-up mode does not affect it: the shareable version is always a whole prompt.

## Extra care with anatomy and continuity

A tick box under Follow-up mode adds a block to the end of whatever you build: the ordinary prompt, a follow-up, and the shareable version alike. It sets out what correct bodies, object counts and continuity look like, and it is worth turning on when a model has started giving people an extra limb, drawing two of something that exists once, or letting details drift between panels of the same image.

Every line is written as what the finished picture shows rather than as something to avoid. An image model has no true negative field, so naming a mistake puts the word into the prompt and can summon the thing it names. "Each arm begins at a shoulder" works where a ban on misplaced arms does not.

Each rule gives a default and then stands aside for whatever the prompt, a character description or a reference has established. That distinction matters: a rule that simply asserted two arms would have a model quietly "correct" an established limb difference, prosthesis or deliberate asymmetry, and a rule that asserted one of every object would fight the Props module that asks for too many mugs. So the block says two arms and two legs where nothing else is established, and says to draw an established difference accurately and consistently where one is.

The block covers counting the frame before finishing it, limbs and where they join, hands, faces, matching pairs, objects appearing in the number the prompt establishes and keeping their identity as they move through the scene, straps and cables following paths that work, people and objects keeping coherent forms of their own, things meeting the surfaces that hold them up, lighting agreeing with its sources, characters and objects staying the same across panels, and their number, scale, orientation, depth and relative position holding from panel to panel until the story changes them.

The setting is remembered on the device and saved with a setup.

## Saved setups

A setup keeps a combination you liked: the master, the ticked modules, the dials and the text boxes. Name it, press **Save**, and it appears in the list with **Load** and **Delete** beside it.

Setups are stored in that browser only and never include your cast or your photos. Modules are recorded by their wording rather than their number, so a setup still loads the right modules after you add or remove packs. Loading a setup tells you how many of its modules apply under the master it was saved with.

## Keyboard

- `Ctrl` or `Cmd` with `Enter` assembles.
- `Ctrl` or `Cmd` with `Shift` and `C` copies the result.
- `/` focuses the module search.

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

Module text, dial text, variation options, field wrappers and the `wording` strings can use `{1}` to `{5}`, or up to `{9}` if a pack raises `maxCast`. Each resolves to the name in that cast slot, or to "somebody" if the slot is empty. This is how the built in scene modules survive a change of cast: write `{1} has stepped on a squeaky floorboard` rather than naming anyone directly.

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

### wording

Every line the app itself contributes to the prompt. Anything not set here keeps its built in value, so a pack can change one phrase without restating the rest. `packs/controls/40-wording.json` ships the complete set at its default values as a working copy to edit.

```json
{
  "wording": {
    "castHeading": "CAST",
    "thisImageHeading": "THIS IMAGE",
    "moduleLine": "{LABEL}: {v}",
    "followUpOpen": "Keep the previous image exactly as it is...",
    "followUpItem": "- {v}",
    "followUpClose": "Do not redraw anything else..."
  }
}
```

The keys are `castHeading`, `castWithPhotos`, `castWithoutPhotos`, `outfitRule`, `missingPhotoOne`, `missingPhotoMany`, `descriptionOpen`, `listTwo`, `listMany`, `thisImageHeading`, `moduleLine`, `dialsHeading`, `variationHeading`, `defaultSection`, `followUpOpen`, `followUpItem` and `followUpClose`, plus the shareable prompt's own strings: `publicIntro`, `publicCharacters`, `publicCastIntro`, `publicCastWhoPerson`, `publicCastWhoAnimal`, `publicCastName`, `publicCastField` and `publicCastRepeat`.

Tokens are replaced where they make sense: `{v}` is the value, `{NAME}` and `{name}` the character's name in capitals and as typed, `{names}` a joined list of names, and `{LABEL}` and `{label}` a category name. Name tokens like `{1}` work here too. An unrecognised token is left alone.

`defaultSection` is only used by a field that does not set its own `section`, and `followUpItem` wraps each line of a follow-up prompt.

### settings

```json
{ "settings": { "maxCast": 5, "variationPools": 3 } }
```

- `maxCast` is how many cast slots the app offers, from 1 to 9. Raising it also widens the usable name tokens, so with `"maxCast": 7` the tokens `{1}` to `{7}` all resolve.
- `variationPools` is how many pools the Vary button draws from. Set it to `0` to switch variation off entirely.

### castFields

The per-character boxes, and the sentence each one contributes to the prompt. Matching an existing `key` changes just that field, a new `key` adds a box, and `"drop": true` removes one.

```json
{
  "castFields": [
    { "key": "voice", "label": "Voice", "hint": "How they sound.",
      "line": "Sounds like {v}.", "order": 15, "promptOrder": 15 },
    { "key": "manner", "drop": true }
  ]
}
```

- `order` places the box on the page; `promptOrder` places its sentence in the prompt. They deliberately differ in the built in set, where the signifier box sits first but its sentence comes after the appearance.
- `line` is the sentence, with `{v}` for what was typed and `{name}` for the character. Any trailing full stop is trimmed from the value first, so the template controls the punctuation.
- `outfitRule: true` marks a field as clothing. The rule about outfits changing between images is only added when a non animal character has something in such a field.
- `name`, `kind`, the photo and the written description are structural and are not cast fields.

### discipline

The lines added by the anatomy and continuity tick box. Matching an existing `id` re-words that rule, a new `id` adds one, `"drop": true` removes one, and `order` places it. `packs/controls/50-discipline.json` ships the built in set as a working copy.

```json
{
  "discipline": [
    { "id": "hands", "text": "Each hand has four fingers and one thumb." },
    { "id": "face", "drop": true },
    { "id": "mine", "order": 5, "text": "A rule of your own." }
  ]
}
```

Write each line as the state the picture is in rather than as a prohibition. The whole point of the block is that it says what is there rather than what is not.

Your text is used exactly as you wrote it; the app does not edit or reject a rule. It does read them, though, and if one is phrased as something to avoid it says so on the page and names the rule, because a rule written that way quietly undoes what the block is for. The built in rules are checked by a test and contain no such phrasing.

That check reads wording rather than meaning. It looks for the usual turns of phrase and nothing more, so a sentence can be negative in substance while using none of them. Treat a quiet result as "none of the usual phrases appeared" rather than as proof.

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

Pools the Vary button draws from. Each pool contributes at most one line, and the app uses the first three pools unless a pack changes `settings.variationPools`. Add pools with a low `order` if you want them to be the ones that fire.

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

A pack containing `"private": true` at the top level is never sent to the public page. The built in cast pack uses this, because it describes real people. On the admin page, press **Load private packs into this browser** once and they are stored in that browser's local storage, so your cast travels with your device rather than with the site. **Forget them again** removes them from that browser, and clears the cast being remembered for Restore when that cast came from one of those packs. Otherwise the cast would outlive the pack it arrived in, and Restore could bring back somebody you had just forgotten. A cast remembered from a public pack is left alone.

Uploads accept JSON only, are capped at 512 KB, must contain a recognised pack key, and are written with a sanitised filename into `uploads/`, which is the only writable path. Packs in `packs/` are read only and can only be changed on the server.

## Updating an existing copy

`install.sh` unpacks a patch archive into the directory it sits in. Put the script and the archive side by side in the folder you want to update and run it:

```
/srv/prompt-bench/install.sh
/srv/prompt-bench/prompt-bench-patch.zip
$ ./install.sh
```

It finds the archive beside itself, so no arguments are needed unless there is more than one. Wrapper directories inside the archive are discovered and skipped, so an archive shaped like `Prompt-Bench/release/prompt-bench.html` installs `prompt-bench.html` beside the script rather than burying it two folders down. Hidden files are included.

Files already in the folder that the patch does not mention are left alone, so your `uploads`, your `deploy/.env` and anything else local survive. Files the patch supplies replace their counterparts. Nothing is deleted unless the patch carries a `DELETE.txt` listing exactly what to remove, one path per line.

Before writing anything it reads the archive and refuses it outright if any entry points outside itself, and it unpacks to a temporary directory that is cleaned up whether the install succeeds or fails. `--dry-run` shows what would happen and writes nothing. `--backup` keeps a copy of whatever it is about to overwrite.

`tools/make-patch.sh` builds an archive in the shape the installer expects, leaving out `.env` and the uploads folder.

## Running it on a server

`server.py` is a read only server with Basic Auth. When the app is served by it, the app fetches `api/packs` on load and merges every JSON file under `packs/` automatically, with no folder picker. Adding a pack becomes: put the file in the folder, reload the page. The `deploy/` folder has a Dockerfile and Compose file, and `DEPLOY.md` is the brief to hand to whoever runs your VPS.

Opened directly from disk the app behaves exactly as before and ignores the server features.

## DLC wave two

`packs/dlc2/` fills out the thin categories: more moods, framing, print finishes, canvas shapes and in image text options, plus a further media set covering animation techniques, street and public art, craft surfaces and deliberately ugly digital media.

## A note on writing modules

Modules work best written as something to do rather than something to avoid. Image models have no true negative field, so a banned word still enters the prompt and can summon the thing it names. The one fixed ban list lives in the shared core block, stated once. Everything else occupies the space positively so the default has nowhere to land.
