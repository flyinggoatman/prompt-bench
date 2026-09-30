# Unlock codes

An unlock code lets somebody open gated packs without signing in. Typing a
right code in the Studio (press <kbd>`</kbd>, use "Enter a code" in the Packs
panel, or Ctrl K → "Enter an unlock code") gives that browser a signed cookie
naming the groups the code opens. The cookie lasts `BENCH_UNLOCK_DAYS` days
(180 by default). A code never opens the admin page.

## Groups: how a code opens a pack

A pack is gated by one of two flags, and names the group that opens it:

```json
{ "pack": "Cast: Ada", "private": true, "unlock": "ada", "people": [] }
{ "pack": "Demo: locked extras", "locked": true, "unlock": "example", "categories": [] }
```

- `"private": true` is for personal material: real people, private wording.
  It is gated on the server and is **never** published.
- `"locked": true` is for ordinary content that simply waits for a code, such
  as the demo pack. It is gated on the server the same way, but it is safe to
  publish.
- `"unlock"` is a group name, or a list of them. A code opens a pack when the
  code grants any group the pack names. A group of `*` opens every gated pack.

A code can grant several groups at once (`alice+bob`). A browser that
enters a second code keeps its first groups and gains the new ones.

The group `nsfw` is special: a browser holding it may show NSFW content (see
`DLC-FORMAT-GUIDE.md`). A code marked NSFW grants it automatically.

## Where codes come from

Two places, merged:

1. **The codes database**, `uploads/unlock-codes.db`, edited from the admin
   page. Move it with `BENCH_CODES_DB=/some/other/path`.
2. **The environment**, `BENCH_UNLOCK_CODES=CODE:group,PAIR:one+two`. These
   still work, show on the admin page read only, and are changed only in `.env`.
   A code in both places opens the union of their groups.

If the database file is missing, the server runs on the environment's codes
and the first save from the admin page creates it. If the file cannot be
parsed, the server logs it, runs on the environment's codes, and refuses to
overwrite it until it is fixed or removed.

## The database format

UTF-8 JSON text. The `.db` name only stops the server and the agent tools from
treating it as a pack.

```json
{
  "format": "prompt-bench-unlock-codes",
  "version": 1,
  "codes": [
    {
      "code": "DEMO1234",
      "category": "examples",
      "label": "Example content",
      "groups": ["example"],
      "nsfw": false,
      "expires": null,
      "disabled": false,
      "notes": "Example code supplied with the public build.",
      "created": "2026-09-25T00:00:00Z",
      "updated": "2026-09-25T00:00:00Z"
    }
  ],
  "revoked": [
    { "id": "1a2b3c4d", "at": "2026-09-25T00:00:00Z", "note": "" }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `format`, `version` | Identify the file. Always `"prompt-bench-unlock-codes"` and `1`. |
| `code` | What people type. Letters and digits, 4 to 32, stored upper case. Case, spaces and dashes are ignored when typed. |
| `category` | Your own grouping for the admin list: `people`, `examples`, anything. |
| `label` | Who or what the code is for. Shown on the admin page only. |
| `groups` | The unlock groups it opens. Letters, digits, `-`, `_`, or `*`. |
| `nsfw` | `true` also grants the `nsfw` group. |
| `expires` | `"YYYY-MM-DD"`, or `null` for never. From that day it opens nothing new. |
| `disabled` | `true` keeps the entry but makes it open nothing. |
| `notes` | Free text for you. |
| `created`, `updated` | UTC timestamps written by the server. |
| `revoked[].id` | A redemption id that no longer works. |

Other top-level keys are kept when the admin page saves, so notes written into
the file by hand survive.

Saving writes `unlock-codes.db.tmp` first and renames it over the real file,
so a reader never sees half a file. The `.tmp` file only exists for that
instant; if one is left behind after a crash it can be deleted.

**Never commit a database that holds real codes.** Both files are in
`.gitignore`. The public build replaces it with fictional demonstration codes.

## Redemptions and revoking

Every right code gives the browser a redemption id, logged with the time,
code, address and browser in `uploads/unlock-redemptions.jsonl` and in
`docker logs`. The admin page's Redemptions card lists them.

- **Revoke** locks that one browser out at once, with no restart. It is stored
  in the database's `revoked` list. **Let back in** removes it.
- `BENCH_UNLOCK_REVOKED` in the environment revokes ids too; those can only be
  undone in `.env`.
- To keep somebody out for good, also disable or change the code they know,
  or they can type it again.

A group stops working for every browser the moment no live code grants it any
more (deleted, disabled or expired), even for browsers that entered it earlier.

## The admin page and API

The admin page's Unlock codes card adds, edits, disables, expires and deletes
codes. It calls these routes, which need the admin sign-in and a same-site
JSON request:

| Route | Does |
| --- | --- |
| `GET /api/codes` | Every database code, the environment's codes, categories and revoked ids. |
| `POST /api/codes/save` | Add a code, or change one when `"was"` names the code being edited. Adding a code that already exists is refused. |
| `POST /api/codes/delete` | `{"code": "..."}` removes it. |
| `GET /api/unlock/redemptions` | The redemption log. |
| `POST /api/unlock/revoke` | `{"id": "..."}` revokes, `{"id": "...", "undo": true}` lets back in. |
| `POST /api/admin/nsfw-override` | `{"on": true}` lifts the real-person NSFW block for the signed-in session only. |

## Making your own demo groups

1. Make a pack with `"locked": true` and `"unlock": "yourgroup"` (never
   `private` unless it holds personal material). `packs/examples/90-demo-locked.json`
   is a working example.
2. On the admin page, add a code with `yourgroup` in its groups.
3. Type the code in the Studio. The pack appears; Packs → Lock again removes it.
