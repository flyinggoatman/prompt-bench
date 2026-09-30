# Using Prompt Bench from an agent

Everything a person can do at the page, software can do without one: read what
is installed, choose from it, and assemble the prompt. It is the same engine
either way. `tools/bench-engine.js` is lifted out of `prompt-bench.html` by the
build, so the page and the command line cannot drift into disagreeing.

## The short version

An agent that can only browse needs one URL:

```
/api/agent/compose?brief=A+risograph+poster+of+three+friends,+no+text&format=text
```

An agent that can read a page should start at `/llms.txt`. The landing page,
`/home`, links every page and carries the same directory as JSON in
`<script type="application/json" id="bench-directory">`. An agent driving a
headless browser should open `/studio#agent`, the Agent desk: one form with
stable ids (`#agent-brief`, `#agent-cast`, `#agent-compose`) and the results in
`#agent-prompt`, `#agent-shareable`, `#agent-gaps` and `#agent-questions`, with
`#agent-status[data-ready]` saying whether anything still blocks the prompt. The
page also exposes `window.PromptBench` (`manifest()`, `compose(input)`,
`suggest(brief)`, `gaps()`, `apply(recipe)`, `assemble(mode)`), and carries its
manifest as JSON in `<script id="pb-agent-manifest">`.

## Compose: a client's words in, a finished prompt out

`compose` is what `tools/bench-agent.js` adds on top of the engine, and the page,
the command line and the server all run the same file.

```json
{
  "bench": "main",
  "brief": "A candid moment of me and my sister in a kitchen, watercolour. No phones.",
  "cast": [{ "name": "Sam", "marker": "green beanie", "looks": "tall, thirties" },
           { "name": "Jo", "marker": "red glasses", "photo": true }],
  "recipe": { "dials": { "energy": 3 } },
  "fill": "empty"
}
```

It works out what the words can justify and nothing more:

- the cast size ("me and my sister", "the three of us", "just me"), unless a
  cast or a count was given;
- the master, from the words people use for each ("poster", "candid", "comic
  strip", "avatar");
- one module per lane, only where the words are specific enough: two
  distinctive matches, or one rare word in a lane where one word is decisive
  ("risograph", "beach", "beard"). A word spent choosing one lane cannot choose
  another, and nothing is matched against what the client asked to leave out;
- dials from plain words ("calm", "chaotic", "warm", "no text");
- quoted words become exact lettering, with the words dial raised to fit;
- "no phones" goes to the keep-out field, which is capped, and not into the
  brief text, where naming a thing tends to summon it.

Anything given explicitly wins. The reply carries `prompt`, `followup`,
`shareable`, the `recipe` it built, every `decision` with its reason, the `gaps`
still open, a `questions` message ready to send to the client, `ready` (no
blockers), and `shareableLeaks` (cast names or typed text found in the
shareable version, normally empty).

### Gaps

Each gap has a `level` (`blocker`, `should`, `could`, `note`), a `question` in
words a client understands, and `fill.path` saying where the answer goes
(`cast[1].name`, `fields.context`, `modules` with a `category`, `dials.words`).
Lanes that need a choice carry `options`. Answer by composing again with the
same brief and the answers added.

## Over HTTP, without signing in

The agent routes are open. Without a session they read the public packs only,
which is exactly what the shareable prompt is built from, so an agent can never
reach a private cast; signed in, they read everything. The `X-Pack-Scope`
header says which. They are metered at 90 requests a minute per address.

```
GET  /llms.txt                         the guide
GET  /openapi.json                     the routes, as OpenAPI 3.1
GET  /api/agent                        the manifest
GET  /api/agent/compose?brief=...      &cast=Name (repeat) &castCount=N &master=A
                                       &module=wording (repeat) &fill=none &seed=N
                                       &recipe=<base64url> &mode=shareable &format=text
POST /api/agent/compose                the JSON above
POST /api/agent/suggest                {"brief": "..."}
POST /api/agent/gaps                   {"recipe": {...}}
```

## As an MCP server

`POST /mcp` speaks the Model Context Protocol over plain HTTP: stateless
JSON-RPC, one JSON answer per request. Add `https://your-host/mcp` to any MCP
client as a remote HTTP server. Tools:

- `compose_prompt` { brief, cast, recipe, context, fill, bench, mode }
- `suggest_from_brief` { brief, bench }
- `list_gaps` { recipe, bench }
- `get_manifest` { bench }
- `list_modules` { category, bench }

Same scope and rate limit as `/api/agent`.

Three ways in, in order of how little they need:

- **The command line.** `node tools/bench-cli.js` beside the packs. No server.
- **The server routes.** `/api/agent/...`, open to anyone with the public packs,
  and reading the private packs too for a signed-in visitor.
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

With the server running (public packs without a session, every pack with one):

```
GET  /api/agent/capabilities?bench=main
GET  /api/agent/model?bench=persona
POST /api/agent/offered     {"recipe": {...}}
POST /api/agent/assemble    {"recipe": {...}, "mode": "prompt"}
```

These need Node on the server, because they run the same engine rather than a
second implementation of it. Without Node they answer 501 and say so.

From the command line, the same layer:

```bash
node tools/bench-cli.js manifest --public
node tools/bench-cli.js compose --brief "a risograph poster of the three of us, no text"
node tools/bench-cli.js compose --input job.json --json
node tools/bench-cli.js suggest --brief "gouache portrait, green palette" --bench persona
node tools/bench-cli.js questions --recipe recipe.json
```

`--public` leaves out every pack marked private, as the public server does.

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
