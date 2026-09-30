# Membership

The Prompt Bench website is free. A membership is a one-off payment that opens
the **MCP tools** and the **agent API** to a member's own AI assistant. It never
opens a private pack: a member reads the public packs, exactly like a visitor.

Membership is off unless `BENCH_MEMBERSHIP=1`. With it off, everything behaves
as it always has and the MCP and agent API are free.

## What needs a membership

| Free for everyone | Needs a member token (or the owner's sign-in) |
| --- | --- |
| The website: `/`, Studio, Classic, Persona | MCP `tools/call` (every tool) |
| MCP `initialize`, `ping`, `tools/list` | `GET /api/agent/compose`, `GET /api/agent/model` |
| `/llms.txt`, `/openapi.json` | `POST /api/agent/{compose,suggest,gaps,assemble,offered,recipe}` |
| `/api/agent` (manifest), `/api/agent/capabilities` | |
| `/membership` and `/api/membership` | |

Without a token, an MCP tool call returns a normal tool result marked as an
error, saying membership is required and linking to `/membership`, so the
person's assistant shows them the message. The HTTP routes answer:

| Status | `code` | When |
| --- | --- | --- |
| 401 | `membership_required` | no token |
| 401 | `token_invalid`, `token_revoked`, `token_expired` | the token does not work |
| 403 | `membership_inactive`, `token_scope` | the token is fine, the membership is not |
| 429 | `rate_limited` | more than `BENCH_TOKEN_RATE` calls a minute on one token, or many unknown tokens from one address |
| 503 | `busy` | more than `BENCH_ENGINE_SLOTS` compositions at once, for longer than `BENCH_ENGINE_WAIT` seconds |
| 503 | `membership_unavailable` | the members database cannot be opened |

## Tokens

A token looks like `pb_` followed by 32 characters. It is shown **once**, when
it is made; the server keeps only its SHA-256. Members send it on every call:

```
Authorization: Bearer pb_...
```

Claude Code:

```
claude mcp add --transport http prompt-bench https://YOUR-HOST/mcp --header "Authorization: Bearer pb_..."
```

A member can see their membership and tokens, and replace a token, on
`/membership` by pasting it. Replacing a token stops the old one at once.

Clients that can only sign in through a web page (OAuth, such as connector
directories) are not supported yet.

## Where the data lives

`data/members.db`, a SQLite database on its own volume (`./data:/app/data`),
owned by the container user like `uploads/`. `install.sh` creates `data/` with
the right owner. Move it with `BENCH_MEMBERS_DB`. It is in `.gitignore`: never
commit it.

| Table | Holds |
| --- | --- |
| `members` | name, email, notes, the payment provider's customer id |
| `entitlements` | the membership: `active` or `revoked`, `disputed`, optional `ends_at`, where it came from |
| `credentials` | tokens as hashes, their label, scopes (`mcp`, `agent`), last use, revocation |
| `checkout_sessions` | a paid checkout and whether its welcome token has been shown |
| `provider_events` | every Stripe event, stored before it is acted on |
| `usage_events` | the route and outcome of paid calls. **Never** the brief, cast or prompt |

Request logs record paths without their query strings, and never headers, so
neither a brief nor a token reaches `docker logs`.

Back up with `deploy/backup.sh`, which copies the database with SQLite's online
backup (safe while the server runs) and archives `uploads/`. Restore: stop the
container, copy a backup over `data/members.db` and delete `data/members.db-wal`
and `data/members.db-shm`, start the container.

## Managing members by hand

The admin page's **Members** card adds a member, grants or ends a membership,
restores one, issues and revokes tokens, and lists recent payment events. This
works before any payment provider exists, for a hand-run pilot.

Owner routes (admin sign-in, same-site JSON): `GET /api/members`,
`POST /api/members/create`, `update`, `grant`, `entitlement`, `token`,
`revoke-token`.

## Stripe

Stripe proves a payment happened; Prompt Bench decides access. The server never
calls Stripe, holds no API key and never sees a card. It receives signed events
at `POST /api/stripe/webhook` and checks the signature on the raw body before
anything else. A repeated delivery of an event changes nothing.

| Stripe event | Membership |
| --- | --- |
| `checkout.session.completed` or `.async_payment_succeeded`, paid, one-off | lifetime membership |
| `charge.refunded`, full | ends at once |
| `charge.refunded`, partial | unchanged |
| `charge.dispute.created` / `.updated` | continues, marked disputed |
| `charge.dispute.closed`, lost | ends |
| `charge.dispute.closed`, won or other | continues, mark cleared |
| `customer.subscription.deleted` (future monthly plans) | continues to the end of the paid period |

Set up (test mode first):

1. In Stripe, make a product and a one-off price, and a Payment Link or Checkout
   for it. Set its success URL to `https://YOUR-HOST/membership?session_id={CHECKOUT_SESSION_ID}`.
2. Add a webhook endpoint `https://YOUR-HOST/api/stripe/webhook` for the events
   above, and copy its signing secret.
3. In `.env`: `BENCH_MEMBERSHIP=1`, `STRIPE_WEBHOOK_SECRET=whsec_...`,
   `BENCH_MEMBERSHIP_CHECKOUT_URL=https://buy.stripe.com/...`,
   `BENCH_MEMBERSHIP_PRICE=£…`. If the Stripe account sells anything else, also
   `BENCH_STRIPE_PAYMENT_LINKS=plink_...`, or put `product=mcp_membership` in the
   checkout's metadata.
4. Recreate the container.

After paying, the buyer lands on `/membership?session_id=...`. The page asks the
server for the token, which exists only once the verified event has arrived; the
address alone grants nothing. It shows the token once and never again.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `BENCH_MEMBERSHIP` | off | `1` turns the paid gate on |
| `BENCH_MEMBERS_DB` | `data/members.db` | the database file |
| `BENCH_MEMBERSHIP_URL` | `/membership` | where refusals send people |
| `BENCH_MEMBERSHIP_CHECKOUT_URL` | none | the Stripe checkout or Payment Link |
| `BENCH_MEMBERSHIP_PRICE` | none | the price as shown on `/membership` |
| `BENCH_TOKEN_RATE` | 60 | calls a minute per token |
| `BENCH_ENGINE_SLOTS` | 4 | compositions at once, across everyone |
| `BENCH_ENGINE_WAIT` | 10 | seconds a call waits for a slot before `busy` |
| `STRIPE_WEBHOOK_SECRET` | none | the webhook's signing secret |
| `BENCH_STRIPE_PAYMENT_LINKS` | none | Payment Link ids that sell the membership |
