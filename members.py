"""Prompt Bench members: who has paid for the hosted service, and their tokens.

Standard library only, like server.py. One SQLite file on its own volume
(BENCH_MEMBERS_DB, default data/members.db). Nothing here decides pack scope:
membership opens the paid service (the MCP tools and the agent API), never a
private pack. The server's access policy asks this module one question, "is
this token an active member with this scope?", and nothing else.

Tables
  members            one row per paying person or organisation
  entitlements       what a member may use, and until when (product_key, status)
  credentials        bearer tokens, stored only as a SHA-256 hash
  checkout_sessions  a paid checkout, and whether its welcome token was shown
  provider_events    every payment provider event, stored before it is acted on
  usage_events       successful and refused calls, without any prompt text

Tokens look like pb_<32 url-safe characters>. They are random enough that a
plain SHA-256 is the right store: nothing to salt against, and a lookup by
hash is exact. The raw token is returned once, when it is made, and never
again.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time

PRODUCT = "mcp_membership"          # the one product so far: MCP and agent API access
SCOPES = ("mcp", "agent")           # what a token may be used for
TOKEN_PREFIX = "pb_"

_LOCK = threading.Lock()            # one writer at a time, on top of SQLite's own locking

MIGRATIONS = [
    # 1: the first schema.
    """
    CREATE TABLE members (
        member_id            TEXT PRIMARY KEY,
        name                 TEXT NOT NULL DEFAULT '',
        email                TEXT NOT NULL DEFAULT '',
        notes                TEXT NOT NULL DEFAULT '',
        provider             TEXT,
        provider_customer_id TEXT,
        created_at           TEXT NOT NULL,
        updated_at           TEXT NOT NULL
    );
    CREATE UNIQUE INDEX members_provider ON members(provider, provider_customer_id)
        WHERE provider_customer_id IS NOT NULL;

    CREATE TABLE entitlements (
        entitlement_id TEXT PRIMARY KEY,
        member_id      TEXT NOT NULL REFERENCES members(member_id),
        product_key    TEXT NOT NULL,
        status         TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
        disputed       INTEGER NOT NULL DEFAULT 0,
        starts_at      TEXT NOT NULL,
        ends_at        TEXT,
        source         TEXT NOT NULL,
        source_ref     TEXT,
        reason         TEXT NOT NULL DEFAULT '',
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    );
    CREATE INDEX entitlements_member ON entitlements(member_id);
    CREATE INDEX entitlements_ref ON entitlements(source_ref);

    CREATE TABLE credentials (
        credential_id TEXT PRIMARY KEY,
        member_id     TEXT NOT NULL REFERENCES members(member_id),
        token_hash    TEXT NOT NULL UNIQUE,
        prefix        TEXT NOT NULL,
        label         TEXT NOT NULL DEFAULT '',
        scopes        TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        last_used_at  TEXT,
        expires_at    TEXT,
        revoked_at    TEXT
    );
    CREATE INDEX credentials_member ON credentials(member_id);

    CREATE TABLE checkout_sessions (
        session_id      TEXT PRIMARY KEY,
        member_id       TEXT NOT NULL REFERENCES members(member_id),
        entitlement_id  TEXT NOT NULL REFERENCES entitlements(entitlement_id),
        paid_at         TEXT NOT NULL,
        token_issued_at TEXT
    );

    CREATE TABLE provider_events (
        provider     TEXT NOT NULL,
        event_id     TEXT NOT NULL,
        event_type   TEXT NOT NULL,
        received_at  TEXT NOT NULL,
        processed_at TEXT,
        status       TEXT NOT NULL,
        detail       TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (provider, event_id)
    );

    CREATE TABLE usage_events (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id     TEXT,
        credential_id TEXT,
        route         TEXT NOT NULL,
        outcome       TEXT NOT NULL,
        at            TEXT NOT NULL
    );
    CREATE INDEX usage_member ON usage_events(member_id, at);
    """,
]


def now_iso(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t if t is not None else time.time()))


def new_id(kind):
    return kind + "_" + secrets.token_hex(8)


def hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def looks_like_token(raw):
    return isinstance(raw, str) and raw.startswith(TOKEN_PREFIX) and 20 <= len(raw) <= 80


class Store:
    """The members database. Safe to share between the server's threads: every
    call opens its own short-lived connection, and writes take one lock."""

    def __init__(self, path):
        self.path = path
        self.error = ""
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self._migrate()
        except (OSError, sqlite3.Error) as exc:
            # A server without a writable data volume still runs: membership
            # simply reports itself unavailable instead of taking the site down.
            self.error = "%s: %s" % (path, exc)

    @property
    def ok(self):
        return not self.error

    # ---------------- plumbing ----------------

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 10000")
        return db

    def _migrate(self):
        with _LOCK:
            db = self._connect()
            try:
                db.execute("PRAGMA journal_mode = WAL")
                db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
                row = db.execute("SELECT version FROM schema_version").fetchone()
                have = row["version"] if row else 0
                if not row:
                    db.execute("INSERT INTO schema_version (version) VALUES (0)")
                for i, sql in enumerate(MIGRATIONS, start=1):
                    if i <= have:
                        continue
                    db.execute("BEGIN IMMEDIATE")
                    try:
                        for stmt in [s for s in sql.split(";") if s.strip()]:
                            db.execute(stmt)
                        db.execute("UPDATE schema_version SET version = ?", (i,))
                        db.execute("COMMIT")
                    except Exception:
                        db.execute("ROLLBACK")
                        raise
            finally:
                db.close()

    def _read(self, sql, args=()):
        db = self._connect()
        try:
            return [dict(r) for r in db.execute(sql, args).fetchall()]
        finally:
            db.close()

    def _write(self, fn):
        """Run fn(db) inside one IMMEDIATE transaction and return its result."""
        with _LOCK:
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                try:
                    out = fn(db)
                    db.execute("COMMIT")
                    return out
                except Exception:
                    db.execute("ROLLBACK")
                    raise
            finally:
                db.close()

    # ---------------- members ----------------

    def create_member(self, name="", email="", notes="", provider=None, provider_customer_id=None):
        mid, t = new_id("mem"), now_iso()

        def go(db):
            db.execute("INSERT INTO members (member_id, name, email, notes, provider, provider_customer_id,"
                       " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                       (mid, name[:120], email[:200], notes[:500], provider, provider_customer_id, t, t))
            return mid
        return self._write(go)

    def member(self, member_id):
        rows = self._read("SELECT * FROM members WHERE member_id = ?", (member_id,))
        return rows[0] if rows else None

    def member_by_provider(self, provider, provider_customer_id):
        rows = self._read("SELECT * FROM members WHERE provider = ? AND provider_customer_id = ?",
                          (provider, provider_customer_id))
        return rows[0] if rows else None

    def update_member(self, member_id, **fields):
        allowed = {k: str(v)[:500] for k, v in fields.items() if k in ("name", "email", "notes")}
        if not allowed:
            return

        def go(db):
            sets = ", ".join("%s = ?" % k for k in allowed) + ", updated_at = ?"
            db.execute("UPDATE members SET " + sets + " WHERE member_id = ?",
                       list(allowed.values()) + [now_iso(), member_id])
        self._write(go)

    def list_members(self):
        """Everything the admin page shows, newest first. Never a token."""
        members = self._read("SELECT * FROM members ORDER BY created_at DESC")
        ents = self._read("SELECT * FROM entitlements ORDER BY created_at")
        creds = self._read("SELECT credential_id, member_id, prefix, label, scopes, created_at, last_used_at,"
                           " expires_at, revoked_at FROM credentials ORDER BY created_at")
        uses = self._read("SELECT member_id, COUNT(*) AS n, MAX(at) AS last FROM usage_events"
                          " WHERE outcome = 'ok' GROUP BY member_id")
        by = {m["member_id"]: dict(m, entitlements=[], credentials=[], uses=0, lastUse=None) for m in members}
        for e in ents:
            if e["member_id"] in by:
                by[e["member_id"]]["entitlements"].append(dict(e, live=entitlement_live(e)))
        for c in creds:
            if c["member_id"] in by:
                by[c["member_id"]]["credentials"].append(c)
        for u in uses:
            if u["member_id"] in by:
                by[u["member_id"]]["uses"], by[u["member_id"]]["lastUse"] = u["n"], u["last"]
        return list(by.values())

    # ---------------- entitlements ----------------

    def grant(self, member_id, product_key=PRODUCT, source="manual", source_ref=None, ends_at=None, reason=""):
        eid, t = new_id("ent"), now_iso()

        def go(db):
            db.execute("INSERT INTO entitlements (entitlement_id, member_id, product_key, status, starts_at,"
                       " ends_at, source, source_ref, reason, created_at, updated_at)"
                       " VALUES (?,?,?,'active',?,?,?,?,?,?,?)",
                       (eid, member_id, product_key, t, ends_at, source, source_ref, reason[:200], t, t))
            return eid
        return self._write(go)

    def set_entitlement(self, entitlement_id, status=None, disputed=None, ends_at=None, reason=None):
        def go(db):
            row = db.execute("SELECT * FROM entitlements WHERE entitlement_id = ?", (entitlement_id,)).fetchone()
            if not row:
                raise KeyError("no such entitlement")
            new = dict(row)
            if status is not None:
                if status not in ("active", "revoked"):
                    raise ValueError("status is active or revoked")
                new["status"] = status
            if disputed is not None:
                new["disputed"] = 1 if disputed else 0
            if ends_at is not None:
                new["ends_at"] = ends_at or None
            if reason is not None:
                new["reason"] = reason[:200]
            db.execute("UPDATE entitlements SET status = ?, disputed = ?, ends_at = ?, reason = ?, updated_at = ?"
                       " WHERE entitlement_id = ?",
                       (new["status"], new["disputed"], new["ends_at"], new["reason"], now_iso(), entitlement_id))
            return new
        return self._write(go)

    def entitlements_by_ref(self, source_ref):
        return self._read("SELECT * FROM entitlements WHERE source_ref = ?", (source_ref,))

    def active_entitlement(self, member_id, product_key=PRODUCT):
        for e in self._read("SELECT * FROM entitlements WHERE member_id = ? AND product_key = ?",
                            (member_id, product_key)):
            if entitlement_live(e):
                return e
        return None

    # ---------------- credentials ----------------

    def issue_token(self, member_id, label="", scopes=SCOPES, expires_at=None):
        """A new bearer token. Returns (credential_id, raw_token); the raw token
        is not stored and cannot be shown again."""
        raw = TOKEN_PREFIX + secrets.token_urlsafe(24)
        cid, t = new_id("cred"), now_iso()
        scopes = [s for s in scopes if s in SCOPES]

        def go(db):
            if not db.execute("SELECT 1 FROM members WHERE member_id = ?", (member_id,)).fetchone():
                raise KeyError("no such member")
            db.execute("INSERT INTO credentials (credential_id, member_id, token_hash, prefix, label, scopes,"
                       " created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                       (cid, member_id, hash_token(raw), raw[:10], label[:80], " ".join(scopes), t, expires_at))
            return cid
        self._write(go)
        return cid, raw

    def revoke_token(self, credential_id):
        def go(db):
            n = db.execute("UPDATE credentials SET revoked_at = ? WHERE credential_id = ? AND revoked_at IS NULL",
                           (now_iso(), credential_id)).rowcount
            return n > 0
        return self._write(go)

    def rotate_token(self, credential_id):
        """Revoke one token and issue its replacement, same member, label and scopes."""
        rows = self._read("SELECT * FROM credentials WHERE credential_id = ?", (credential_id,))
        if not rows:
            raise KeyError("no such credential")
        old = rows[0]
        new = self.issue_token(old["member_id"], old["label"], old["scopes"].split(), old["expires_at"])
        self.revoke_token(credential_id)
        return new

    def verify(self, raw, scope):
        """Who a bearer token belongs to, if it may use this scope right now.

        Returns (identity, reason). identity is None unless the token exists,
        is not revoked or expired, carries the scope, and its member holds a
        live entitlement. reason is a stable code for the caller.
        """
        if not looks_like_token(raw):
            return None, "token_invalid"
        rows = self._read("SELECT * FROM credentials WHERE token_hash = ?", (hash_token(raw),))
        # The lookup is by exact hash; compare again in constant time so the
        # decision never depends on a partial match.
        if not rows or not hmac.compare_digest(rows[0]["token_hash"], hash_token(raw)):
            return None, "token_invalid"
        cred = rows[0]
        if cred["revoked_at"]:
            return None, "token_revoked"
        if cred["expires_at"] and cred["expires_at"] <= now_iso():
            return None, "token_expired"
        if scope not in cred["scopes"].split():
            return None, "token_scope"
        ent = self.active_entitlement(cred["member_id"])
        if not ent:
            return None, "membership_inactive"
        self._touch(cred["credential_id"])
        return {"member_id": cred["member_id"], "credential_id": cred["credential_id"],
                "prefix": cred["prefix"], "entitlement_id": ent["entitlement_id"],
                "disputed": bool(ent["disputed"]), "ends_at": ent["ends_at"]}, "ok"

    def credential_for(self, raw):
        """The credential behind a token, whatever its membership state, for
        the member's own status page. None for an unknown or revoked token."""
        if not looks_like_token(raw):
            return None
        rows = self._read("SELECT * FROM credentials WHERE token_hash = ?", (hash_token(raw),))
        if not rows or rows[0]["revoked_at"] or not hmac.compare_digest(rows[0]["token_hash"], hash_token(raw)):
            return None
        return rows[0]

    def _touch(self, credential_id):
        # last_used_at to the minute is plenty, and keeps writes rare.
        t = now_iso()[:16] + ":00Z"

        def go(db):
            db.execute("UPDATE credentials SET last_used_at = ? WHERE credential_id = ?"
                       " AND (last_used_at IS NULL OR last_used_at < ?)", (t, credential_id, t))
        try:
            self._write(go)
        except sqlite3.Error:
            pass

    def status_for(self, member_id):
        """What a member may see about themselves. No other member, no hashes."""
        m = self.member(member_id)
        if not m:
            return None
        ents = self._read("SELECT entitlement_id, product_key, status, disputed, starts_at, ends_at"
                          " FROM entitlements WHERE member_id = ? ORDER BY created_at", (member_id,))
        creds = self._read("SELECT credential_id, prefix, label, scopes, created_at, last_used_at, expires_at,"
                           " revoked_at FROM credentials WHERE member_id = ? ORDER BY created_at", (member_id,))
        uses = self._read("SELECT COUNT(*) AS n FROM usage_events WHERE member_id = ? AND outcome = 'ok'",
                          (member_id,))
        return {"member": {"id": m["member_id"], "name": m["name"], "since": m["created_at"]},
                "entitlements": [dict(e, live=entitlement_live(e)) for e in ents],
                "credentials": creds, "uses": uses[0]["n"] if uses else 0}

    # ---------------- usage ----------------

    def record_use(self, member_id, credential_id, route, outcome):
        def go(db):
            db.execute("INSERT INTO usage_events (member_id, credential_id, route, outcome, at) VALUES (?,?,?,?,?)",
                       (member_id, credential_id, route[:60], outcome[:40], now_iso()))
        try:
            self._write(go)
        except sqlite3.Error:
            pass

    # ---------------- checkout sessions ----------------

    def record_checkout(self, session_id, member_id, entitlement_id):
        def go(db):
            db.execute("INSERT OR IGNORE INTO checkout_sessions (session_id, member_id, entitlement_id, paid_at)"
                       " VALUES (?,?,?,?)", (session_id, member_id, entitlement_id, now_iso()))
        self._write(go)

    def checkout(self, session_id):
        rows = self._read("SELECT * FROM checkout_sessions WHERE session_id = ?", (session_id,))
        return rows[0] if rows else None

    def claim_welcome_token(self, session_id):
        """The token for a paid checkout, exactly once.

        Returns (raw_token, None) the first time, (None, reason) afterwards or
        when the session is unknown. Claiming and issuing happen in one
        transaction, so two tabs racing get one token between them.
        """
        box = {}

        def go(db):
            row = db.execute("SELECT * FROM checkout_sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row:
                return "pending"
            if row["token_issued_at"]:
                return "already_shown"
            ent = db.execute("SELECT * FROM entitlements WHERE entitlement_id = ?", (row["entitlement_id"],)).fetchone()
            if not ent or not entitlement_live(dict(ent)):
                return "membership_inactive"
            raw = TOKEN_PREFIX + secrets.token_urlsafe(24)
            t = now_iso()
            db.execute("INSERT INTO credentials (credential_id, member_id, token_hash, prefix, label, scopes, created_at)"
                       " VALUES (?,?,?,?,?,?,?)",
                       (new_id("cred"), row["member_id"], hash_token(raw), raw[:10], "from checkout",
                        " ".join(SCOPES), t))
            db.execute("UPDATE checkout_sessions SET token_issued_at = ? WHERE session_id = ?", (t, session_id))
            box["raw"] = raw
            return "ok"
        reason = self._write(go)
        return (box.get("raw"), None) if reason == "ok" else (None, reason)

    # ---------------- provider events ----------------

    def begin_event(self, provider, event_id, event_type):
        """Store an event before acting on it. Returns False when it was already
        processed, so a retried delivery changes nothing."""
        def go(db):
            row = db.execute("SELECT status FROM provider_events WHERE provider = ? AND event_id = ?",
                             (provider, event_id)).fetchone()
            if row and row["status"] in ("processed", "ignored"):
                return False
            if not row:
                db.execute("INSERT INTO provider_events (provider, event_id, event_type, received_at, status)"
                           " VALUES (?,?,?,?,'received')", (provider, event_id, event_type, now_iso()))
            return True
        return self._write(go)

    def finish_event(self, provider, event_id, status, detail=""):
        def go(db):
            db.execute("UPDATE provider_events SET status = ?, detail = ?, processed_at = ?"
                       " WHERE provider = ? AND event_id = ?", (status, detail[:300], now_iso(), provider, event_id))
        self._write(go)

    def events(self, limit=100):
        return self._read("SELECT * FROM provider_events ORDER BY received_at DESC LIMIT ?", (limit,))

    # ---------------- backup ----------------

    def backup_to(self, target):
        """A consistent copy of the live database, safe while the server runs."""
        src = self._connect()
        try:
            dst = sqlite3.connect(target)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()


def entitlement_live(e, now=None):
    """Active, and not past its end date. A dispute does not end access: the
    owner's rule is that access continues until the dispute is lost."""
    if e.get("status") != "active":
        return False
    ends = e.get("ends_at")
    return not ends or ends > (now or now_iso())


def export_json(store):
    """Everything except token hashes, for the admin page's download."""
    return json.dumps({"members": store.list_members(), "events": store.events(500)}, indent=2)
