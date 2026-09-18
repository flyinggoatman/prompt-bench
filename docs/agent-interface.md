# Using Prompt Bench from an agent

Everything a person can do at the page, software can do without one: read what
is installed, choose from it, and assemble the prompt. It is the same engine
either way. `tools/bench-engine.js` is lifted out of `prompt-bench.html` by the
build, so the page and the command line cannot drift into disagreeing.

Three ways in, in order of how little they need:

- **The command line.** `node tools/bench-cli.js` beside the packs. No server.
- **The server routes.** `/api/agent/...`, behind the same password as the admin
  page, because the engine reads private packs too.
- **A link.** A setup encoded in a URL, so an agent and a person can hand a
  configuration to each other in a chat message.

## Start by asking what this build is

```bash
node tools/bench-cli.js capabilities
node tools/bench-cli.js capabilities --bench persona
```

It answers with the bench, the masters and the cast sizes each is written for,
every category and how many modules it holds, every dial with its range, the
text fields, the modes it can build, and the switches it has. Read this rather
than assuming: a build's packs decide all of it, and two installs differ.

## Then ask what is installed

```bash
node tools/bench-cli.js model                    # everything
node tools/bench-cli.js model --category SCENE   # one category
```

Every module comes back with its number, its wording, the masters it belongs
to, how many characters it needs, the wording it uses for smaller casts, and
whether it brings people from outside the cast.

## A recipe is what you write down

A recipe is a small JSON document describing one prompt. It addresses modules by
their wording rather than their number, because numbers move when packs change.

```json
{
  "recipe": 1,
  "bench": "main",
  "name": "One person, quiet",
  "master": "A",
  "modules": ["Mock album cover. Square, figure dense, all three crammed onto a small sofa."],
  "castCount": 1,
  "cast": [{ "name": "Wren", "kind": "person", "looks": "tall, forties" }],
  "dials": { "energy": 2 },
  "fields": { "context": "A ferry crew of one." },
  "discipline": true,
  "strangers": false,
  "castOpen": false,
  "seed": 412
}
```

Every key but `recipe` is optional. `castCount` decides how many characters the
prompt is about; `strangers` decides whether anybody outside the cast may
appear; `castOpen` decides whether the prompt invites whoever runs it to add
more. `seed` makes the variation reproducible: the same recipe and the same seed
produce the same prompt, every time.

## Build from it

```bash
node tools/bench-cli.js assemble --recipe recipe.json
node tools/bench-cli.js assemble --recipe recipe.json --mode followup
node tools/bench-cli.js assemble --recipe recipe.json --mode shareable
echo '{"recipe":1,"master":"A"}' | node tools/bench-cli.js assemble --recipe -
```

`prompt` is the whole thing, `followup` is the short edit instruction for when
the last image was nearly right, and `shareable` is the version for somebody
else: no names, no photographs, no private packs, a blank form where the cast
would be.

Add `--json` to get the text wrapped with its word count instead of raw.

## When a recipe does not fit

The command refuses rather than quietly building something else, and says which
of three things went wrong: the module is not installed, it belongs to another
master, or the cast is too small and it has no wording for that size. Fix the
recipe, or pass `--force` to build without the modules that did not apply.

```bash
node tools/bench-cli.js offered --recipe recipe.json
```

lists what this recipe can and cannot use, with the reason for each, which is
usually the faster way to find out before assembling.

## Over HTTP

With the server running, and the admin password:

```
GET  /api/agent/capabilities?bench=main
GET  /api/agent/model?bench=persona
POST /api/agent/offered     {"recipe": {...}}
POST /api/agent/assemble    {"recipe": {...}, "mode": "prompt"}
```

These need Node on the server, because they run the same engine rather than a
second implementation of it. Without Node they answer 501 and say so.

## Handing a setup to a person

The page's **Copy link** button produces a URL carrying the master, the modules,
the dials, the text boxes and the switches. Opening it sets the page up exactly
that way. An agent can build one the same way: base64url of the recipe JSON,
after `#recipe=`.

A link never carries a cast or a photograph, for the same reason a saved setup
does not. Whoever opens it fills in their own people.

## What the engine will not do

It will not invent a cast, add a character the recipe did not ask for, or
silently swap wording. Where a module needs more characters than the recipe
has, it uses the wording written for that size, and where there is none it says
so rather than pretending.
