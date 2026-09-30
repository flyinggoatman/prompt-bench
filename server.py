#!/usr/bin/env python3
# Prompt Bench server. Standard library only.
#
# Public, no authentication:
#   GET  /                 the app (Studio; BENCH_HOME=classic serves the classic page,
#                          BENCH_HOME=home the landing page)
#   GET  /home /studio /classic /persona
#   GET  /api/packs        every pack NOT marked private, main bench unless
#                          ?bench=persona asks otherwise
#   GET  /healthz
#
# For AI agents. Public packs when not signed in, every pack when signed in;
# the X-Pack-Scope header says which:
#   GET  /llms.txt  /agents  /openapi.json
#   GET  /api/agent                          the manifest: what this is and how to drive it
#   GET  /api/agent/compose?brief=...        brief in, finished prompt out (browse-only agents)
#   GET  /api/agent/{capabilities,model,manifest}
#   POST /api/agent/{compose,suggest,gaps,assemble,offered,recipe}
#
# Unlock codes, for the people in a private pack who would rather not sign in:
#   POST /api/unlock {"code": "..."}   a right code sets a signed cookie
#   GET  /api/unlock                   which groups this browser has unlocked, and its redemption id
#   POST /api/unlock/forget            lock again
#   GET  /api/unlock/redemptions       (signed in) who redeemed which code, when, from where
#   POST /api/unlock/revoke            (signed in) lock one redemption out, or let it back in
#   GET  /api/codes                    (signed in) every code: the database's and the environment's
#   POST /api/codes/save               (signed in) add or change a code in the database
#   POST /api/codes/delete             (signed in) remove a code from the database
#   POST /api/admin/nsfw-override      (signed in) let this admin session use NSFW with real people
# Codes come from two places. uploads/unlock-codes.db is the codes database the
# admin page edits (JSON text, see CODES_DB below). BENCH_UNLOCK_CODES in the
# environment still works and is shown read only. Neither is ever served. A code
# opens private packs that name one of its groups ("unlock": "cast"), is read
# only, and never grants the admin page. A code marked NSFW also opens the
# "nsfw" group, which is what lets a browser show NSFW content at all.
#
# MCP (Model Context Protocol) over HTTP, for agents with tool support:
#   POST /mcp                          JSON-RPC: initialize, tools/list, tools/call
#
# Membership (off unless BENCH_MEMBERSHIP=1; members.py keeps the records):
# with it on, MCP tools/call and the agent routes that run the engine need a
# member's bearer token (Authorization: Bearer pb_...) or the owner's sign-in.
# Discovery stays free: MCP initialize and tools/list, /llms.txt, /openapi.json,
# /api/agent (the manifest) and /api/agent/capabilities. The website itself
# never needs a membership: it runs the engine in the browser.
#   GET  /membership                   what membership is, status, and the welcome page
#   GET  /api/membership               public: is membership on, and where to get it
#   GET  /api/membership/status        (member token) the member's own record
#   POST /api/membership/rotate        (member token) replace this token
#   GET  /api/membership/welcome       ?session_id=... the token for a paid checkout, once
#   GET  /api/members                  (signed in) every member, entitlement and token (no secrets)
#   POST /api/members/{create,update,grant,entitlement,token,revoke-token}   (signed in)
#   POST /api/stripe/webhook           Stripe events, verified by signature
#
# Only the files named in STATIC are ever served. Pack files, uploads, the
# server source and the tools are reached through the API or not at all, so a
# private pack cannot be read by asking for its path.
#
# Authenticated with HTTP Basic (BENCH_USER / BENCH_PASS):
#   GET  /admin            the management page
#   GET  /api/packs?all=1  every pack including private ones
#
# A correct password also issues a session cookie, so the bench page can ask
# for /api/packs?all=auto and receive the private packs without a second
# password box. Not signed in, ?all=auto is the public list and never a
# challenge: a visitor is not asked for a password by the page they came to
# use. Sessions are in memory and last twelve hours.
#   POST /api/upload       add a JSON pack to uploads/
#   POST /api/remove       delete a pack from uploads/
#   POST /api/import-github import valid Prompt Bench JSON packs from a GitHub repository
#
# Writes are confined to the uploads directory. GitHub import accepts only
# github.com repository links, downloads a bounded archive, parses JSON, and
# installs only files containing recognised Prompt Bench pack keys.

import base64
import hashlib
import hmac
import http.cookies
import secrets
import threading
import time
import http.server
import shutil
import subprocess
import io
import json
import os
import posixpath
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

# members.py and billing.py sit beside this file; make that true however the
# server is started or imported.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import billing  # noqa: E402
import members  # noqa: E402

ROOT = os.path.abspath(os.path.dirname(__file__))
PACKS = os.path.join(ROOT, "packs")
UPLOADS = os.path.join(ROOT, "uploads")
PORT = int(os.environ.get("BENCH_PORT", "8080"))
USER = os.environ.get("BENCH_USER", "")
PASS = os.environ.get("BENCH_PASS", "")
MAX_UPLOAD = 512 * 1024
MAX_GITHUB_ARCHIVE = int(float(os.environ.get("BENCH_GITHUB_MAX_MB", "25")) * 1024 * 1024)
# A pack released as a .zip inside a repository is read too, one level deep,
# within these bounds, so a zip cannot expand into something unreasonable.
MAX_NESTED_ZIP = 8 * 1024 * 1024
MAX_NESTED_ZIP_ENTRIES = 500
MAX_GITHUB_JSON_FILES = 250
MAX_GITHUB_PACKS = 150
HOME = os.environ.get("BENCH_HOME", "studio").strip().lower()
# Behind Traefik every request arrives from the proxy's address, so per-address
# limits would put every visitor in one bucket. Set BENCH_TRUST_PROXY=1 when a
# proxy you control sets X-Forwarded-For; never when the port is exposed directly.
TRUST_PROXY = os.environ.get("BENCH_TRUST_PROXY", "").strip() in ("1", "true", "yes")

# Membership. Off by default, so a server upgraded without a data volume
# behaves exactly as before.
MEMBERSHIP = os.environ.get("BENCH_MEMBERSHIP", "").strip() in ("1", "true", "yes")
MEMBERS_DB = os.environ.get("BENCH_MEMBERS_DB") or os.path.join(ROOT, "data", "members.db")
# Where somebody without a membership is sent: the page that explains it, or a
# checkout link once one exists.
MEMBERSHIP_URL = os.environ.get("BENCH_MEMBERSHIP_URL", "").strip()
MEMBERSHIP_CHECKOUT_URL = os.environ.get("BENCH_MEMBERSHIP_CHECKOUT_URL", "").strip()
MEMBERSHIP_PRICE = os.environ.get("BENCH_MEMBERSHIP_PRICE", "").strip()
STORE = members.Store(MEMBERS_DB) if MEMBERSHIP else None
if STORE is not None and not STORE.ok:
    sys.stderr.write("membership is on but the members database is unavailable (%s); paid routes will "
                     "answer 503 until it is fixed\n" % STORE.error)
# Per token, successful or not: a member's own agent loop cannot starve others.
TOKEN_RATE = int(os.environ.get("BENCH_TOKEN_RATE", "60"))
TOKEN_HITS = {}
# The engine is a Node subprocess per call (about 110 ms on this server). A
# few at once is plenty on two cores; the rest wait briefly, then get "busy".
ENGINE_SLOTS = threading.BoundedSemaphore(int(os.environ.get("BENCH_ENGINE_SLOTS", "4")))
ENGINE_WAIT = float(os.environ.get("BENCH_ENGINE_WAIT", "10"))
# The engine routes a membership pays for. Everything else under /api/agent
# (the manifest and capabilities) is discovery and stays free.
PAID_AGENT_GET = ("compose", "model")
PAID_AGENT_POST = ("assemble", "offered", "recipe", "compose", "suggest", "gaps")


def parse_unlock_codes(raw):
    """BENCH_UNLOCK_CODES="CODE:group,PAIR:one+two,MASTER:*" -> {"CODE": {"group"}, ...}.

    Codes are compared case-insensitively and must be letters and digits only.
    One code may open several groups, joined with +. A group of * opens every
    private pack.
    """
    out = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        code, _, group = part.partition(":")
        code = re.sub(r"[^A-Za-z0-9]", "", code).upper()
        group = (group or "*").strip() or "*"
        if len(code) < 4:
            sys.stderr.write("Ignoring an unlock code shorter than four characters.\n")
            continue
        out.setdefault(code, set()).update(g.strip() for g in group.split("+") if g.strip())
    return out


ENV_CODES = parse_unlock_codes(os.environ.get("BENCH_UNLOCK_CODES", ""))
UNLOCK_COOKIE = "bench_unlock"
UNLOCK_TTL = int(os.environ.get("BENCH_UNLOCK_DAYS", "180")) * 24 * 60 * 60
# Signing key for the unlock cookie. Derived from the admin password unless one
# is given, so changing the password also locks every unlocked browser.
UNLOCK_SECRET = (os.environ.get("BENCH_SECRET") or "").encode("utf-8")
# Every redemption gets its own id, carried in the cookie, so one shared code
# can still be told apart browser by browser. An id listed here stops working
# at once; the browser can only get back in by typing a code again.
ENV_REVOKED = set(x.strip().lower() for x in os.environ.get("BENCH_UNLOCK_REVOKED", "").split(",") if x.strip())
UNLOCK_LOG = os.environ.get("BENCH_UNLOCK_LOG") or os.path.join(ROOT, "uploads", "unlock-redemptions.jsonl")

# The codes database. JSON text in the one writable folder, named .db rather
# than .json so nothing mistakes it for a pack. It may be missing: the server
# then runs on the environment's codes alone, and the first save from the admin
# page creates it. Its shape:
#   {"format": "prompt-bench-unlock-codes", "version": 1,
#    "codes":   [{"code", "category", "label", "groups", "nsfw", "expires",
#                 "disabled", "notes", "created", "updated"}],
#    "revoked": [{"id", "at", "note"}]}
CODES_DB = os.environ.get("BENCH_CODES_DB") or os.path.join(ROOT, "uploads", "unlock-codes.db")
CODES_FORMAT = "prompt-bench-unlock-codes"
NSFW_GROUP = "nsfw"
GROUP_RE = re.compile(r"^(\*|[A-Za-z0-9][A-Za-z0-9_-]{0,39})$")
_CODES_CACHE = {"stamp": None, "doc": None}

# Every file the server will hand out as a file, and who may have it. Anything
# else is a 404, directories included, so there is no listing to browse.
STATIC = {
    "/prompt-bench-home.html": "public",
    "/membership.html": "public",
    "/prompt-bench-studio.html": "public",
    "/prompt-bench.html": "public",
    "/persona-bench.html": "public",
    # Signed in only: this old page still carries the private cast. A public
    # build replaces it with a sanitised copy.
    "/legacy/prompt-bench-v2.html": "public",
    "/prompt-bench-offline.html": "auth",
    "/admin.html": "auth",
    "/admin-persona.html": "auth",
}
ROUTES = {
    "/home": "/prompt-bench-home.html",
    "/membership": "/membership.html",
    "/studio": "/prompt-bench-studio.html",
    "/classic": "/prompt-bench.html",
    "/persona": "/persona-bench.html",
    "/admin": "/admin.html",
    "/admin-persona": "/admin-persona.html",
}

# Failed sign ins per address. Five wrong passwords in ten minutes and that
# address waits out the rest of the window: enough for a typo, useless for
# guessing.
AUTH_FAILS = {}
AUTH_WINDOW = 600
AUTH_LIMIT = 5
# The agent routes run the engine in a subprocess, so they are metered.
AGENT_RATE = 90          # requests per minute per address
AGENT_HITS = {}
MCP_BATCH = 10
LOCK = threading.Lock()
AGENT_CACHE = {}
SAFE = re.compile(r"[^A-Za-z0-9._-]")
KNOWN_PACK_KEYS = (
    "shared", "masters", "people", "categories", "wording", "settings",
    "castFields", "discipline", "dials", "variation", "fields"
)

if not USER or not PASS:
    sys.stderr.write("BENCH_USER and BENCH_PASS must both be set. Refusing to start.\n")
    sys.exit(2)

EXPECTED = "Basic " + base64.b64encode((USER + ":" + PASS).encode("utf-8")).decode("ascii")
if not UNLOCK_SECRET:
    UNLOCK_SECRET = hashlib.sha256(("prompt-bench-unlock:" + USER + ":" + PASS).encode("utf-8")).digest()


# ---------------- the codes database ----------------

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clean_code(raw):
    return re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()


def blank_codes_doc():
    return {"format": CODES_FORMAT, "version": 1, "codes": [], "revoked": []}


def load_codes_doc():
    """The database as a dict, read again only when the file changes.

    A missing file is an empty database, never an error. A file that will not
    parse is also treated as empty, loudly, so a hand edit gone wrong cannot
    take the whole site down; the admin page says so rather than overwriting it.
    """
    try:
        st = os.stat(CODES_DB)
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return blank_codes_doc()
    with LOCK:
        if _CODES_CACHE["stamp"] == stamp and _CODES_CACHE["doc"] is not None:
            return _CODES_CACHE["doc"]
    try:
        with open(CODES_DB, encoding="utf-8") as fh:
            doc = json.load(fh)
        if not isinstance(doc, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        sys.stderr.write("the codes database %s could not be read (%s); running on the environment's codes\n"
                         % (CODES_DB, exc))
        doc = dict(blank_codes_doc(), broken=str(exc))
    doc.setdefault("codes", [])
    doc.setdefault("revoked", [])
    if not isinstance(doc["codes"], list):
        doc["codes"] = []
    if not isinstance(doc["revoked"], list):
        doc["revoked"] = []
    with LOCK:
        _CODES_CACHE["stamp"], _CODES_CACHE["doc"] = stamp, doc
    return doc


def save_codes_doc(doc):
    """Write the whole database at once: a temporary file, then a rename, so a
    reader never sees half of it."""
    if doc.get("broken"):
        raise ValueError("the codes database on disk could not be read, so it was not overwritten: fix or remove "
                         + os.path.basename(CODES_DB) + " first")
    doc = dict(doc)
    doc["format"], doc["version"] = CODES_FORMAT, 1
    os.makedirs(os.path.dirname(CODES_DB), exist_ok=True)
    tmp = CODES_DB + ".tmp"
    with LOCK:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, CODES_DB)
        _CODES_CACHE["stamp"] = None


def code_groups(entry):
    """The groups one database entry opens. NSFW adds the nsfw group."""
    groups = entry.get("groups")
    if isinstance(groups, str):
        groups = groups.replace(",", "+").split("+")
    out = set(str(g).strip() for g in (groups or []) if str(g).strip())
    if entry.get("nsfw"):
        out.add(NSFW_GROUP)
    return out


def code_expired(entry, now=None):
    exp = str(entry.get("expires") or "").strip()
    if not exp:
        return False
    return exp[:10] < time.strftime("%Y-%m-%d", time.gmtime(now or time.time()))


def live_codes():
    """Every code that works right now: {"CODE": {"groups": set, "source": "db"|"env"|"both"}}.

    The database's codes that are not disabled or past their expiry date, and
    the environment's. A code in both places opens the union of their groups.
    """
    out = {}
    for code, groups in ENV_CODES.items():
        out[code] = {"groups": set(groups), "source": "env"}
    for entry in load_codes_doc()["codes"]:
        if not isinstance(entry, dict):
            continue
        code = clean_code(entry.get("code"))
        if len(code) < 4 or entry.get("disabled") or code_expired(entry):
            continue
        have = out.get(code)
        if have:
            have["groups"] |= code_groups(entry)
            have["source"] = "both" if have["source"] != "db" else "db"
        else:
            out[code] = {"groups": code_groups(entry), "source": "db"}
    return out


def revoked_ids():
    ids = set(ENV_REVOKED)
    for r in load_codes_doc()["revoked"]:
        rid = str((r.get("id") if isinstance(r, dict) else r) or "").strip().lower()
        if rid:
            ids.add(rid)
    return ids


def validate_code_entry(raw, existing=None):
    """A database entry from the admin page, checked and normalised, or ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("expected a code as a JSON object")
    code = clean_code(raw.get("code"))
    if len(code) < 4:
        raise ValueError("a code needs at least four letters or digits")
    if len(code) > 32:
        raise ValueError("a code can be at most 32 characters")
    groups = raw.get("groups")
    if isinstance(groups, str):
        groups = groups.replace(",", "+").split("+")
    groups = [str(g).strip() for g in (groups or []) if str(g).strip()]
    for g in groups:
        if not GROUP_RE.match(g):
            raise ValueError("a group is letters, digits, - and _ (or * for everything): " + g)
    nsfw = bool(raw.get("nsfw"))
    if not groups and not nsfw:
        raise ValueError("a code must open at least one group, or be marked NSFW")
    category = re.sub(r"\s+", " ", str(raw.get("category") or "").strip())[:40] or "general"
    expires = str(raw.get("expires") or "").strip()
    if expires and not re.match(r"^\d{4}-\d{2}-\d{2}$", expires):
        raise ValueError("expiry is a date as YYYY-MM-DD, or empty for never")
    entry = {
        "code": code,
        "category": category,
        "label": str(raw.get("label") or "").strip()[:80],
        "groups": sorted(set(groups)),
        "nsfw": nsfw,
        "expires": expires or None,
        "disabled": bool(raw.get("disabled")),
        "notes": str(raw.get("notes") or "").strip()[:500],
        "created": (existing or {}).get("created") or now_iso(),
        "updated": now_iso(),
    }
    return entry


def sign_unlock(groups, rid):
    body = base64.urlsafe_b64encode(json.dumps(
        {"g": sorted(groups), "id": rid, "exp": int(time.time()) + UNLOCK_TTL}, separators=(",", ":")).encode()).decode().rstrip("=")
    mac = hmac.new(UNLOCK_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
    return body + "." + mac


def read_unlock_doc(token):
    """(groups, redemption id) from a signed unlock cookie, or (empty set, "")."""
    try:
        body, mac = token.rsplit(".", 1)
        good = hmac.new(UNLOCK_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(mac, good):
            return set(), ""
        doc = json.loads(base64.urlsafe_b64decode((body + "=" * (-len(body) % 4)).encode()).decode())
        if int(doc.get("exp", 0)) < time.time():
            return set(), ""
        rid = str(doc.get("id") or "").lower()
        if not rid or rid in revoked_ids():
            return set(), ""
        # A group no code grants any more stops working at once, even for
        # browsers that unlocked it earlier.
        live = set()
        for entry in live_codes().values():
            live |= entry["groups"]
        return set(g for g in doc.get("g", []) if g in live), rid
    except Exception:
        return set(), ""


def read_unlock(token):
    """The groups a signed unlock cookie grants, or an empty set."""
    return read_unlock_doc(token)[0]


def log_redemption(entry):
    """One line per redemption, in uploads (the one writable folder) and in the
    server log, so `docker logs` shows it even when the file cannot be written."""
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
    sys.stderr.write("unlock redeemed " + line + "\n")
    try:
        os.makedirs(os.path.dirname(UNLOCK_LOG), exist_ok=True)
        with LOCK:
            with open(UNLOCK_LOG, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError as exc:
        sys.stderr.write("could not write the redemption log: %s\n" % exc)


def read_redemptions(limit=500):
    try:
        with open(UNLOCK_LOG, encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        doc["revoked"] = str(doc.get("id", "")).lower() in revoked_ids()
        out.append(doc)
    return out


def pack_groups(entry):
    d = entry.get("data")
    g = d.get("unlock") if isinstance(d, dict) else None
    if isinstance(g, str):
        return {g}
    if isinstance(g, list):
        return set(str(x) for x in g)
    return set()


def visible_to(entry, groups):
    """A private pack is visible to an unlocked browser whose groups name it."""
    if not is_gated(entry):
        return True
    if "*" in groups:
        return True
    return bool(pack_groups(entry) & groups)


def read_dir(base, tag):
    out = []
    if not os.path.isdir(base):
        return out
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for name in sorted(filenames):
            if not name.lower().endswith(".json"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            try:
                with open(full, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception as exc:
                data = {"pack": "BROKEN " + rel, "_error": str(exc)}
            out.append({"path": rel, "source": tag, "data": data})
    return out


def pack_state_token():
    """A short stamp of the installed packs.

    Two people can use Prompt Bench at once, and only one of them can be
    installing packs. The stamp is what makes that safe: a writer sends back the
    stamp it was looking at, and a write against a stale one is refused rather
    than quietly overwriting somebody else's work. A reader can poll it to
    notice the set has changed underneath them.
    """
    parts = []
    for base in (PACKS, UPLOADS):
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for name in sorted(filenames):
                if not name.lower().endswith(".json"):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    stat = os.stat(full)
                except OSError:
                    continue
                parts.append("%s:%d:%d" % (os.path.relpath(full, ROOT), stat.st_size, int(stat.st_mtime)))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def all_packs():
    return read_dir(PACKS, "packs") + read_dir(UPLOADS, "uploads")


NODE = shutil.which("node")
CLI = os.path.join(ROOT, "tools", "bench-cli.js")


def run_bench_cli(arguments, recipe=None, public=False, payload_flag="--recipe", groups=None):
    """Run the shared engine through its command line.

    The assembler lives in the page and is lifted into tools/bench-engine.js by
    the build, so this route and the page cannot disagree. Reimplementing it
    here in Python is the one thing that would guarantee they eventually do.
    """
    if not NODE:
        raise RuntimeError(
            "the agent interface needs Node on this server: install it, or use "
            "tools/bench-cli.js from a machine that has it"
        )
    if not os.path.isfile(CLI):
        raise RuntimeError("tools/bench-cli.js is missing from this install")
    payload = json.dumps(recipe) if recipe is not None else None
    if payload is not None:
        arguments = arguments + [payload_flag, "-"]
    if public:
        arguments = arguments + ["--public"]
        if groups:
            arguments = arguments + ["--allow-groups", ",".join(sorted(groups))]
    done = subprocess.run(
        [NODE, CLI] + arguments,
        input=payload, capture_output=True, text=True, timeout=30, cwd=ROOT,
    )
    if done.returncode != 0:
        raise ValueError((done.stderr or done.stdout or "the engine refused that request").strip())
    return done.stdout


def pack_bench(entry):
    """Which bench a pack belongs to.

    The pack says so, or its path does, and the declaration wins. The same rule
    runs in both pages, so a file is judged identically wherever it is read.
    """
    d = entry.get("data")
    if isinstance(d, dict) and d.get("bench") in ("main", "persona", "both"):
        return d["bench"]
    path = str(entry.get("path", "")).replace("\\", "/")
    return "persona" if "persona-packs/" in path else "main"


# ---------------- NSFW ----------------
# Anything marked "nsfw": true (a pack, a master, a person, a category or a
# module; a category passes it to its modules, a pack to everything in it) is
# sent only to a browser holding the nsfw group, or to the signed-in owner.
# The agent routes never see it at all: tools/bench-cli.js strips it too.

def is_nsfw_pack(entry):
    d = entry.get("data")
    return bool(isinstance(d, dict) and d.get("nsfw"))


def strip_nsfw_data(d):
    """A copy of one pack's data with every NSFW entry left out."""
    if not isinstance(d, dict):
        return d
    out = dict(d)
    for key in ("masters", "people", "shared", "dials", "variation", "fields", "discipline", "castFields"):
        if isinstance(d.get(key), list):
            out[key] = [x for x in d[key] if not (isinstance(x, dict) and x.get("nsfw"))]
    if isinstance(d.get("categories"), list):
        cats = []
        for c in d["categories"]:
            if not isinstance(c, dict):
                continue
            if c.get("nsfw"):
                continue
            c = dict(c)
            if isinstance(c.get("items"), list):
                c["items"] = [it for it in c["items"] if not (isinstance(it, dict) and it.get("nsfw"))]
            cats.append(c)
        out["categories"] = cats
    return out


def without_nsfw(entries):
    out = []
    for e in entries:
        if is_nsfw_pack(e):
            continue
        e = dict(e)
        e["data"] = strip_nsfw_data(e.get("data"))
        out.append(e)
    return out


# Sessions live in memory only. A restart signs everybody out, which is the
# right trade for a single small server: nothing to persist, nothing to leak,
# and the owner signs in again on the admin page.
SESSION_COOKIE = "bench_session"
SESSION_TTL = 12 * 60 * 60
SESSIONS = {}
# Per-session switches the owner can flip on the admin page. Only one so far:
# using NSFW content with a cast that includes real people, for checking that
# the block works. It lives and dies with the session, deliberately.
SESSION_FLAGS = {}


def new_session():
    prune_sessions()
    token = secrets.token_urlsafe(32)
    with LOCK:
        SESSIONS[token] = time.time() + SESSION_TTL
    return token


def valid_session(token):
    if not token:
        return False
    with LOCK:
        expires = SESSIONS.get(token)
        if expires is None:
            return False
        if expires < time.time():
            SESSIONS.pop(token, None)
            return False
    return True


def end_session(token):
    with LOCK:
        SESSIONS.pop(token, None)
        SESSION_FLAGS.pop(token, None)


def prune_sessions():
    # The server is threaded: without the lock, one request iterating this
    # dict while another adds to it raises and drops the request.
    now = time.time()
    with LOCK:
        for token in [t for t, exp in SESSIONS.items() if exp < now]:
            SESSIONS.pop(token, None)
            SESSION_FLAGS.pop(token, None)


def prune_hits(table, window, now):
    # Called under LOCK. Keeps the per-address tables from growing without
    # bound when many addresses each call once and never come back.
    if len(table) > 10000:
        for addr in [a for a, hits in table.items() if not hits or hits[-1] <= now - window]:
            table.pop(addr, None)


def auth_blocked(addr):
    now = time.time()
    with LOCK:
        prune_hits(AUTH_FAILS, AUTH_WINDOW, now)
        hits = [t for t in AUTH_FAILS.get(addr, []) if t > now - AUTH_WINDOW]
        AUTH_FAILS[addr] = hits
        return len(hits) >= AUTH_LIMIT


def auth_failed(addr):
    with LOCK:
        AUTH_FAILS.setdefault(addr, []).append(time.time())


def agent_allowed(addr):
    now = time.time()
    with LOCK:
        prune_hits(AGENT_HITS, 60, now)
        hits = [t for t in AGENT_HITS.get(addr, []) if t > now - 60]
        if len(hits) >= AGENT_RATE:
            AGENT_HITS[addr] = hits
            return False
        hits.append(now)
        AGENT_HITS[addr] = hits
        return True


def token_allowed(credential_id):
    now = time.time()
    with LOCK:
        prune_hits(TOKEN_HITS, 60, now)
        hits = [t for t in TOKEN_HITS.get(credential_id, []) if t > now - 60]
        if len(hits) >= TOKEN_RATE:
            TOKEN_HITS[credential_id] = hits
            return False
        hits.append(now)
        TOKEN_HITS[credential_id] = hits
        return True


def billing_ready():
    return billing.ready()


def membership_link(base):
    return MEMBERSHIP_URL or (base + "/membership")


def packs_for_bench(entries, bench):
    """What one bench is served. Its own packs and anything marked for both.

    A bench never receives the other's packs. Borrowing a category from the
    other bench happens in the page, on packs it already holds, so nothing has
    to be served twice.
    """
    if bench not in ("main", "persona"):
        return entries
    if bench == "persona":
        # The persona bench borrows the style categories (medium, finish,
        # palette, light...) from the main packs, and the page can only borrow
        # from packs it has been given. The engine keeps just those categories.
        return entries
    return [e for e in entries if pack_bench(e) in (bench, "both")]


def is_gated(entry):
    """Hidden until a code or a sign-in opens it.

    "private" means personal material: it is gated here and never published.
    "locked" means ordinary content that merely waits for a code, such as the
    demo pack a public install ships with: gated here the same way, but safe
    to publish, so the public build keeps it and a demo code can open it.
    """
    d = entry.get("data")
    return bool(isinstance(d, dict) and (d.get("private") or d.get("locked")))


def is_prompt_bench_pack(data):
    return isinstance(data, dict) and any(k in data for k in KNOWN_PACK_KEYS)


def safe_upload_path(name):
    name = os.path.basename(name or "")
    name = SAFE.sub("-", name).strip("-.")
    if not name:
        return None
    if not name.lower().endswith(".json"):
        name += ".json"
    return os.path.join(UPLOADS, name)


def safe_github_upload_name(owner, repo, path):
    path = path.replace("\\", "/").strip("/")
    flat = re.sub(r"[^A-Za-z0-9._-]+", "-", path.replace("/", "--")).strip("-.")
    stem = "gh-%s-%s--%s" % (owner, repo, flat or "pack.json")
    if not stem.lower().endswith(".json"):
        stem += ".json"
    return SAFE.sub("-", stem)[:220]


def persona_upload_path(name):
    """Where a persona import lands.

    The import flattens a repository into one directory, which would lose the
    one thing that says which bench a file is for. Persona packs keep their own
    subdirectory under uploads, so the path rule still recognises them after
    they arrive.
    """
    name = os.path.basename(name or "")
    name = SAFE.sub("-", name).strip("-.")
    if not name:
        return None
    if not name.lower().endswith(".json"):
        name += ".json"
    return os.path.join(UPLOADS, "persona-packs", name)


def parse_github_repo_url(value):
    """(owner, repo, branch or None, folder or "") from the link people actually paste.

    Accepts https://github.com/owner/repo and the common variants: no scheme,
    http, www., a trailing .git or slash, and a /tree/<branch>[/<folder>] or
    /blob/<branch>/<path> link to a branch or folder. Only github.com.
    """
    text = (value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        u = urllib.parse.urlparse(text)
    except Exception:
        return None
    host = (u.hostname or "").lower()
    if u.scheme.lower() not in ("https", "http") or host not in ("github.com", "www.github.com"):
        return None
    parts = [urllib.parse.unquote(p) for p in u.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    valid = re.compile(r"^[A-Za-z0-9_.-]+$")
    if not owner or not repo or not valid.match(owner) or not valid.match(repo):
        return None
    branch, folder = None, ""
    if len(parts) >= 4 and parts[2] in ("tree", "blob"):
        branch = parts[3]
        folder = "/".join(parts[4:])
        if parts[2] == "blob" and "/" in folder:
            folder = folder.rsplit("/", 1)[0]
        elif parts[2] == "blob":
            folder = ""
        if not re.match(r"^[A-Za-z0-9_./-]+$", branch) or ".." in branch.split("/"):
            return None
        if folder and (".." in folder.split("/") or not re.match(r"^[^\x00]+$", folder)):
            return None
    return owner, repo, branch, folder.strip("/")


def github_error_message(exc, used_token):
    """Why GitHub said no, in words a person can act on."""
    code = getattr(exc, "code", 0)
    headers = getattr(exc, "headers", None) or {}
    remaining = headers.get("X-RateLimit-Remaining") if hasattr(headers, "get") else None
    if code in (403, 429) and (remaining == "0" or code == 429):
        reset = headers.get("X-RateLimit-Reset") if hasattr(headers, "get") else None
        when = time.strftime("%H:%M UTC", time.gmtime(int(reset))) if reset and str(reset).isdigit() else "within the hour"
        return ("GitHub's rate limit for this server is used up (it resets at %s). %s"
                % (when, "" if used_token else "Setting GITHUB_TOKEN on the server raises the limit."))
    if code == 401:
        return "GitHub rejected the token. Check GITHUB_TOKEN on the server, or the one-use token."
    if code == 404:
        return ("GitHub found no such repository or branch%s. Check the link; a private repository needs "
                "GITHUB_TOKEN on the server or the one-use token." % ("" if used_token else " visible without a token"))
    if code == 403:
        return "GitHub refused access to that repository (HTTP 403)."
    return "GitHub returned HTTP %d" % code


def github_request(url, token=None, accept=None):
    headers = {
        "User-Agent": "Prompt-Bench-Pack-Importer/1",
        "Accept": accept or "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    return urllib.request.Request(url, headers=headers, method="GET")


def read_limited_response(resp, limit):
    chunks = []
    total = 0
    while True:
        chunk = resp.read(min(65536, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise ValueError("GitHub repository archive is larger than the %d MB import limit" % (limit // 1024 // 1024))
    return b"".join(chunks)


def github_repo_info(owner, repo, token=None):
    url = "https://api.github.com/repos/%s/%s" % (
        urllib.parse.quote(owner, safe=""), urllib.parse.quote(repo, safe="")
    )
    with urllib.request.urlopen(github_request(url, token), timeout=20) as resp:
        raw = read_limited_response(resp, 1024 * 1024)
    info = json.loads(raw.decode("utf-8"))
    branch = info.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise ValueError("GitHub did not report a default branch")
    return branch


def github_zipball(owner, repo, branch, token=None):
    url = "https://api.github.com/repos/%s/%s/zipball/%s" % (
        urllib.parse.quote(owner, safe=""), urllib.parse.quote(repo, safe=""),
        urllib.parse.quote(branch, safe="")
    )
    req = github_request(url, token, "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return read_limited_response(resp, MAX_GITHUB_ARCHIVE)


def write_pack_file(target, pack):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.makedirs(UPLOADS, exist_ok=True)
    tmp = target + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(pack, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, target)


def import_github_repository(url, supplied_token=None, bench="main"):
    parsed = parse_github_repo_url(url)
    if not parsed:
        raise ValueError("use a GitHub repository link such as https://github.com/owner/repository "
                         "(a branch or folder link, /tree/<branch>/<folder>, works too)")
    owner, repo, wanted_branch, folder = parsed
    token = (supplied_token or os.environ.get("GITHUB_TOKEN", "")).strip() or None

    branch = wanted_branch or github_repo_info(owner, repo, token)
    archive = github_zipball(owner, repo, branch, token)

    installed = []
    skipped = []
    json_seen = 0
    pack_seen = 0

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile:
        raise ValueError("GitHub did not return a readable repository archive")

    def members(outer):
        """Every JSON file in the archive, and in any .zip inside it, as
        (repository-relative path, entry, archive it belongs to)."""
        for entry in outer.infolist():
            name = entry.filename.replace("\\", "/")
            if entry.is_dir():
                continue
            if name.lower().endswith(".json"):
                yield name, entry, outer
            elif name.lower().endswith(".zip"):
                if entry.file_size > MAX_NESTED_ZIP:
                    skipped.append({"path": name, "reason": "zip larger than %d MB" % (MAX_NESTED_ZIP // 1024 // 1024)})
                    continue
                try:
                    inner = zipfile.ZipFile(io.BytesIO(outer.read(entry)))
                except Exception:
                    skipped.append({"path": name, "reason": "unreadable zip"})
                    continue
                infos = inner.infolist()
                if len(infos) > MAX_NESTED_ZIP_ENTRIES:
                    skipped.append({"path": name, "reason": "zip has too many files"})
                    continue
                stem = name[:-4]
                for sub in infos:
                    sname = sub.filename.replace("\\", "/")
                    if sub.is_dir() or not sname.lower().endswith(".json") or sname.startswith("__MACOSX/"):
                        continue
                    # The inner path goes under the zip's own name, after the
                    # repository's top folder, exactly like a loose file.
                    yield stem + "/" + sname, sub, inner

    root_prefix = ""
    with zf:
        names = [i.filename for i in zf.infolist()]
        if names and "/" in names[0]:
            root_prefix = names[0].split("/", 1)[0] + "/"
        for name, entry, owner_zip in members(zf):
            if folder:
                inside = name[len(root_prefix):] if name.startswith(root_prefix) else name
                if not (inside == folder or inside.startswith(folder + "/")):
                    continue
            # A bench imports only what belongs to it. The persona bench takes
            # the persona-packs subtree of the repository and nothing else; the
            # main bench takes everything but that subtree.
            in_persona = "persona-packs/" in name
            if bench == "persona" and not in_persona:
                continue
            if bench != "persona" and in_persona:
                continue
            json_seen += 1
            if json_seen > MAX_GITHUB_JSON_FILES:
                raise ValueError("repository contains more than %d JSON files" % MAX_GITHUB_JSON_FILES)
            if entry.file_size > MAX_UPLOAD:
                skipped.append({"path": entry.filename, "reason": "larger than 512 KB"})
                continue

            bits = name.split("/", 1)
            rel = bits[1] if len(bits) > 1 else bits[0]
            if not rel or any(p in ("..", "") for p in rel.split("/")):
                skipped.append({"path": rel or name, "reason": "unsafe path"})
                continue

            try:
                raw = owner_zip.read(entry)
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                skipped.append({"path": rel, "reason": "invalid JSON"})
                continue

            if not is_prompt_bench_pack(data):
                skipped.append({"path": rel, "reason": "not a Prompt Bench pack"})
                continue

            pack_seen += 1
            if pack_seen > MAX_GITHUB_PACKS:
                raise ValueError("repository contains more than %d Prompt Bench pack files" % MAX_GITHUB_PACKS)

            filename = safe_github_upload_name(owner, repo, rel)
            target = persona_upload_path(filename) if bench == "persona" else safe_upload_path(filename)
            if not target:
                skipped.append({"path": rel, "reason": "could not make safe filename"})
                continue
            write_pack_file(target, data)
            installed.append({"path": rel, "saved": os.path.basename(target), "pack": data.get("pack") or rel})

    if not installed:
        where = (" in folder %s" % folder) if folder else ""
        why = ("; %d JSON file(s) were skipped, for example %s: %s" % (len(skipped), skipped[0]["path"], skipped[0]["reason"])
               if skipped else "")
        raise ValueError("no valid Prompt Bench pack JSON files were found in %s/%s (branch %s)%s%s"
                         % (owner, repo, branch, where, why))

    return {
        "ok": True,
        "repository": "%s/%s" % (owner, repo),
        "branch": branch,
        "folder": folder,
        "installed": installed,
        "skipped": skipped,
        "used_token": bool(token),
    }


def membership_guide(base):
    return """
## Membership

This server's MCP tools and agent API are for members. Without a token you can
connect, read this guide, list the MCP tools and read /api/agent, but a tool call
or an engine route answers "membership required" with the link below. The
website itself is free.

Send the member's token on every call:

    Authorization: Bearer pb_...

Membership: {link}
""".format(link=membership_link(base))


def agent_guide(base):
    """The plain text an agent reads first. Served at /llms.txt and /agents.txt."""
    return """# Prompt Bench

> Builds image-generation prompts that leave the image model nothing to invent.
> You give it a client's words; it gives back a finished prompt, the questions
> still worth asking, and a shareable version with every real person removed.

Base: {base}

## Fastest path (one GET, works for browse-only agents)

{base}/api/agent/compose?brief=A+risograph+poster+of+three+friends+at+the+beach,+no+text&format=text

Add &mode=shareable for the version without names, &format=json for everything
(prompt, followup, shareable, recipe, decisions, gaps, questions).

Optional query parameters:
  bench=main|persona        main is scenes with a cast of up to 5; persona is one portrait subject
  cast=Name                 repeat for each character, in order. Or castJson=[{{"name":..,"marker":..}}]
  castCount=N               how many characters, when you know it but not who
  master=A                  a master id from /api/agent/manifest
  module=exact wording      repeat to choose modules yourself; numbers also work
  fill=none                 use only what you set; default fills empty lanes from the brief
  recipe=<base64url>        a recipe as carried after #recipe= in a Studio link
  seed=N                    same inputs and seed always give the same prompt

## Full path (POST JSON)

POST {base}/api/agent/compose
{{"brief": "the client's own words",
  "cast": [{{"name": "Mara", "marker": "yellow enamel flask", "looks": "tall, fifties", "photo": false}}],
  "recipe": {{"master": "B", "modules": ["..."], "dials": {{"energy": 3}}, "fields": {{"context": "..."}}}},
  "fill": "empty"}}

Returns: prompt, followup, shareable, recipe, decisions[], gaps[], questions, ready, shareableLeaks[], link.

Then:
1. If ready is false, answer the blocker gaps (ask the client using 'questions') and POST again with the answers.
2. Give 'prompt' to the image model, with any reference photos attached to the same message.
3. Give 'shareable' to anyone else. It has no names, no photos, no private packs.

## Reading the vocabulary

GET {base}/api/agent/manifest    masters, categories, cast fields, dials, text fields, rules
GET {base}/api/agent/model       every module with its exact wording, number and cast needs
POST {base}/api/agent/suggest    {{"brief": "..."}} -> proposed master, cast size, modules, dials
POST {base}/api/agent/gaps       {{"recipe": {{...}}}} -> what is still open, as questions
POST {base}/api/agent/assemble   {{"recipe": {{...}}, "mode": "prompt|followup|shareable"}}
GET  {base}/openapi.json         the same, as OpenAPI 3.1

## As an MCP server

POST {base}/mcp speaks the Model Context Protocol over HTTP (stateless JSON-RPC).
Tools: compose_prompt, suggest_from_brief, list_gaps, get_manifest, list_modules.
Add it to an MCP client as a remote HTTP server with the URL {base}/mcp.

## In a browser

{base}/studio#agent opens the Agent desk: one form, labelled inputs with stable ids
(#agent-brief, #agent-cast, #agent-compose), outputs in #agent-prompt, #agent-shareable,
#agent-gaps and #agent-recipe. The page also exposes window.PromptBench with
manifest(), compose(input), suggest(brief), gaps(), apply(recipe), assemble(mode).

## Pages

{base}/home                  every page below, also as JSON in #bench-directory
{base}/studio                Prompt Bench Studio
{base}/classic               the classic Prompt Bench page
{base}/persona               Persona Bench
{base}/admin, /admin-persona pack management, Basic Auth

## Rules

- Explicit choices always win. Suggestions only fill what you left empty.
- A cast you give is the whole cast; nobody is added.
- cast[i].photo = true means you will attach a reference photo of that person.
- Put bans in the keep-out field only; everywhere else, say what is there.
- Without sign-in you see public packs only, which is also what the shareable version uses.
""".format(base=base) + (membership_guide(base) if MEMBERSHIP else "")


OPENAPI_PATHS = {
    "/api/agent": {"get": {"summary": "Manifest: what this is, how to drive it, what it accepts"}},
    "/api/agent/manifest": {"get": {"summary": "Manifest for one bench", "parameters": [{"name": "bench", "in": "query", "schema": {"type": "string", "enum": ["main", "persona"]}}]}},
    "/api/agent/model": {"get": {"summary": "Every installed module, master, dial and field", "parameters": [{"name": "bench", "in": "query", "schema": {"type": "string"}}]}},
    "/api/agent/capabilities": {"get": {"summary": "Short capability summary"}},
    "/api/agent/compose": {
        "get": {"summary": "Brief in, prompt out, for agents that can only browse",
                "parameters": [{"name": n, "in": "query", "schema": {"type": "string"}} for n in
                               ("brief", "bench", "cast", "castJson", "castCount", "master", "module", "fill", "recipe", "seed", "mode", "format")]},
        "post": {"summary": "Brief, cast and partial recipe in; prompt, shareable, gaps and questions out",
                 "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {
                     "bench": {"type": "string"}, "brief": {"type": "string"},
                     "cast": {"type": "array", "items": {"type": "object"}},
                     "recipe": {"type": "object"}, "fill": {"type": "string", "enum": ["empty", "none"]},
                     "context": {"type": "string"}, "discipline": {"type": "boolean"}}}}}}}
    },
    "/api/agent/suggest": {"post": {"summary": "Read a brief and propose a recipe without applying it"}},
    "/api/agent/gaps": {"post": {"summary": "What a recipe still leaves open, as questions"}},
    "/api/agent/assemble": {"post": {"summary": "Assemble a recipe in one mode"}},
    "/api/agent/offered": {"post": {"summary": "Which modules a recipe can and cannot use, with reasons"}},
    "/api/agent/recipe": {"post": {"summary": "Normalise and check a recipe"}},
    "/mcp": {"post": {"summary": "Model Context Protocol, stateless JSON-RPC: initialize, tools/list, tools/call"}},
}


class Handler(http.server.BaseHTTPRequestHandler):
    # BaseHTTPRequestHandler rather than SimpleHTTPRequestHandler: this server
    # has no general file serving to fall back on, only the files in STATIC.
    server_version = "PromptBench/3"
    protocol_version = "HTTP/1.0"

    def do_PUT(self): self.send_error(405)
    def do_DELETE(self): self.send_error(405)
    def do_PATCH(self): self.send_error(405)

    # ---------------- identity ----------------

    def client_addr(self):
        if TRUST_PROXY:
            # The right-most entry is the one the proxy itself appended. Anything
            # to its left came from the visitor and may be made up.
            fwd = (self.headers.get("X-Forwarded-For", "") or "").split(",")[-1].strip()
            if fwd:
                return fwd
        return self.client_address[0] if self.client_address else "?"

    def authorised(self):
        """Signed in, by password on this request or by a session from an earlier one.

        Basic Auth alone is not enough. A browser sends those credentials back
        to the path it was challenged on and its children, so a sign in at
        /admin does not reach /api/packs, and the bench page had no way to know
        the person at the keyboard is the owner. A session cookie issued on a
        successful sign in closes that gap without a second password box.

        A wrong password counts against the address it came from, and after
        five in ten minutes that address is not listened to until the window
        passes, even with the right one.
        """
        header = self.headers.get("Authorization", "")
        # A member's bearer token is not a password: it is checked by the
        # membership gate and must never count as a failed sign-in.
        if header and header[:6].lower() == "basic ":
            addr = self.client_addr()
            if auth_blocked(addr):
                self._blocked = True
                return False
            if hmac.compare_digest(header, EXPECTED):
                self.grant_session()
                return True
            auth_failed(addr)
        return valid_session(self.session_token())

    def session_token(self):
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        try:
            jar = http.cookies.SimpleCookie()
            jar.load(raw)
        except Exception:
            return ""
        morsel = jar.get(SESSION_COOKIE)
        return morsel.value if morsel else ""

    def grant_session(self):
        """Issue a session on a password sign in, once per request."""
        if getattr(self, "_session_done", False):
            return
        self._session_done = True
        if valid_session(self.session_token()):
            return
        token = new_session()
        # Secure only where the request actually arrived over HTTPS, so a plain
        # HTTP install on a LAN still works rather than silently dropping the
        # cookie. Traefik and any ordinary proxy set the forwarded header.
        secure = "; Secure" if self.scheme() == "https" else ""
        self._set_cookie = (SESSION_COOKIE + "=" + token + "; Path=/; Max-Age=" + str(SESSION_TTL)
                            + "; HttpOnly; SameSite=Strict" + secure)

    def unlock_doc(self):
        raw = self.headers.get("Cookie", "")
        if not raw:
            return set(), ""
        try:
            jar = http.cookies.SimpleCookie()
            jar.load(raw)
        except Exception:
            return set(), ""
        m = jar.get(UNLOCK_COOKIE)
        return read_unlock_doc(m.value) if m else (set(), "")

    def unlocked_groups(self):
        return self.unlock_doc()[0]

    def scheme(self):
        return (self.headers.get("X-Forwarded-Proto", "") or "http").split(",")[0].strip().lower()

    def host(self):
        # X-Forwarded-Host is only believed from a proxy we trust. Otherwise any
        # visitor could name another site, and the agent manifest (which is
        # cached) would send every later agent there.
        host = (self.headers.get("X-Forwarded-Host") if TRUST_PROXY else None) or self.headers.get("Host") or ""
        return host.split(",")[0].strip()

    def base_url(self):
        return "%s://%s" % (self.scheme(), self.host() or ("127.0.0.1:%d" % PORT))

    def challenge(self):
        if getattr(self, "_blocked", False):
            body = b"Too many wrong passwords from this address. Try again in ten minutes.\n"
            self.send_response(429)
            self.send_header("Retry-After", str(AUTH_WINDOW))
        else:
            body = b"Unauthorised\n"
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Prompt Bench admin", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def same_origin_write(self):
        """Writes come from this site's own pages, as JSON.

        A cross-site form can post text/plain but cannot post JSON without the
        browser asking first, and a browser sends Origin on every cross-site
        POST. Checking both closes the door a cached Basic Auth credential
        would otherwise leave open.
        """
        ctype = (self.headers.get("Content-Type", "") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return False
        origin = self.headers.get("Origin")
        if origin:
            try:
                o = urllib.parse.urlparse(origin)
            except Exception:
                return False
            host = self.host()
            if not host or o.netloc.lower() != host.lower():
                return False
        return True

    # ---------------- responses ----------------

    def json_out(self, obj, code=200, headers=None):
        body = json.dumps(obj, ensure_ascii=False, indent=None).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def text_out(self, text, code=200, ctype="text/plain; charset=utf-8", headers=None):
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def raw_json(self, text, status=200, headers=None):
        return self.text_out(text, status, "application/json; charset=utf-8", headers)

    def not_found(self):
        return self.text_out("Not found\n", 404)

    def serve_file(self, rel, head=False):
        full = os.path.join(ROOT, rel.lstrip("/"))
        if not os.path.isfile(full):
            return self.not_found()
        with open(full, "rb") as fh:
            body = fh.read()
        ctype = "text/html; charset=utf-8" if rel.endswith(".html") else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if STATIC.get(rel) == "auth":
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        else:
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Link", '</llms.txt>; rel="alternate"; type="text/plain"; title="Guide for AI agents"')
        self.end_headers()
        if not head:
            self.wfile.write(body)

    # ---------------- routing ----------------

    def resolve_static(self, path):
        if path == "/":
            if HOME == "home":
                return "/prompt-bench-home.html"
            return "/prompt-bench.html" if HOME == "classic" else "/prompt-bench-studio.html"
        path = path.rstrip("/") or "/"
        return ROUTES.get(path, path if path in STATIC else None)

    def do_HEAD(self):
        path = urllib.parse.urlparse(self.path).path
        rel = self.resolve_static(path)
        if path == "/healthz":
            return self.text_out("")
        if not rel:
            return self.not_found()
        if STATIC[rel] == "auth" and not self.authorised():
            return self.challenge()
        return self.serve_file(rel, head=True)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/healthz":
            return self.text_out("ok\n")

        if path in ("/llms.txt", "/agents.txt", "/.well-known/llms.txt"):
            return self.text_out(agent_guide(self.base_url()))
        if path in ("/agents", "/agents/", "/agent"):
            self.send_response(302)
            self.send_header("Location", "/studio#agent")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/openapi.json":
            return self.json_out({
                "openapi": "3.1.0",
                "info": {"title": "Prompt Bench agent interface", "version": "1",
                         "description": "Public packs without sign-in; every pack with it. Read /llms.txt first."},
                "servers": [{"url": self.base_url()}],
                "paths": OPENAPI_PATHS,
                **({"components": {"securitySchemes": {"member": {
                    "type": "http", "scheme": "bearer",
                    "description": "A Prompt Bench membership token. Needed for the engine routes; "
                                   "see " + membership_link(self.base_url())}}},
                    "security": [{}, {"member": []}]} if MEMBERSHIP else {}),
            })

        if path == "/api/packs":
            packs = all_packs()
            want = (query.get("all") or [""])[0]
            # "auto" is the bench page asking for whatever this visitor is
            # entitled to. Signed in, that includes the private packs and the
            # cast in them. Not signed in, it is exactly the public list, with
            # no password box: a visitor must never be challenged by the page
            # they came to use. "all=1" stays the admin page's explicit ask and
            # still challenges, because there the box is the point.
            signed_in = self.authorised()
            groups = set() if signed_in else self.unlocked_groups()
            if want == "auto":
                if not signed_in:
                    # Unlocked by a code: the public packs plus the private
                    # ones that code's groups name, and nothing else.
                    packs = [p for p in packs if visible_to(p, groups)]
            elif want:
                if not signed_in:
                    return self.challenge()
            else:
                packs = [p for p in packs if not is_gated(p)]
            if not signed_in and NSFW_GROUP not in groups and "*" not in groups:
                packs = without_nsfw(packs)
            bench = (query.get("bench") or ["main"])[0]
            packs = packs_for_bench(packs, bench)
            return self.json_out(packs, headers={
                "X-Pack-Version": pack_state_token(),
                "X-Pack-Scope": "private" if (signed_in and want) else ("unlocked" if (groups and want == "auto") else "public"),
            })

        # Cheap enough to poll: a page uses it to notice that somebody has
        # installed packs since it loaded, and offers a reload rather than
        # reaching in and changing what is on screen.
        if path == "/api/packs/version":
            return self.json_out({"version": pack_state_token()})

        if path == "/api/session":
            return self.json_out({"signedIn": valid_session(self.session_token())})

        if path == "/api/unlock":
            groups, rid = self.unlock_doc()
            names = [p["data"].get("pack") or p["path"] for p in all_packs()
                     if is_gated(p) and groups and visible_to(p, groups)]
            signed_in = valid_session(self.session_token())
            token = self.session_token()
            return self.json_out({"available": bool(live_codes()), "unlocked": sorted(groups), "packs": names,
                                  "id": rid if groups else "",
                                  # May this browser show NSFW content at all, and may it use it
                                  # with real people (the owner's debugging switch, never a visitor's).
                                  "nsfw": signed_in or NSFW_GROUP in groups or "*" in groups,
                                  "realOverride": bool(signed_in and SESSION_FLAGS.get(token, {}).get("nsfwReal"))})

        if path == "/api/unlock/redemptions":
            if not self.authorised():
                return self.challenge()
            return self.json_out({"revoked": sorted(revoked_ids()), "redemptions": read_redemptions()})

        if path == "/api/membership":
            return self.json_out({
                "enabled": MEMBERSHIP,
                "available": bool(STORE is not None and STORE.ok),
                "page": membership_link(self.base_url()),
                "checkout": MEMBERSHIP_CHECKOUT_URL,
                "price": MEMBERSHIP_PRICE,
                "mcp": self.base_url() + "/mcp",
                "free": ["the website: Studio, Classic, Persona and the landing page",
                         "MCP initialize and tools/list", "/llms.txt", "/openapi.json", "/api/agent (manifest)",
                         "/api/agent/capabilities"],
                "paid": ["MCP tools/call"] + ["/api/agent/" + x for x in sorted(set(PAID_AGENT_GET + PAID_AGENT_POST))],
            })

        if path == "/api/membership/status":
            if STORE is None or not STORE.ok:
                return self.json_out({"ok": False, "code": "membership_unavailable", "error": "membership is not available"}, 503)
            addr = "token:" + self.client_addr()
            if auth_blocked(addr):
                return self.json_out({"ok": False, "code": "rate_limited", "error": "too many unknown tokens"}, 429, {"Retry-After": "600"})
            cred = STORE.credential_for(self.bearer())
            if not cred:
                auth_failed(addr)
                return self.json_out({"ok": False, "code": "token_invalid", "error": "that token is not recognised"}, 401,
                                     {"WWW-Authenticate": 'Bearer realm="prompt-bench", error="invalid_token"'})
            doc = STORE.status_for(cred["member_id"])
            doc["ok"], doc["this"] = True, cred["credential_id"]
            return self.json_out(doc, headers={"Cache-Control": "no-store"})

        if path == "/api/membership/welcome":
            if STORE is None or not STORE.ok:
                return self.json_out({"ok": False, "code": "membership_unavailable"}, 503)
            sid = (query.get("session_id") or [""])[0]
            if not re.match(r"^cs_[A-Za-z0-9_]{8,200}$", sid):
                return self.json_out({"ok": False, "code": "bad_session", "error": "that is not a checkout session id"}, 400)
            raw, reason = STORE.claim_welcome_token(sid)
            if not raw:
                messages = {
                    "pending": "Your payment is being confirmed. This page checks again by itself.",
                    "already_shown": "The token for this purchase has already been shown once. If you lost it, contact support.",
                    "membership_inactive": "This purchase no longer has an active membership.",
                }
                return self.json_out({"ok": False, "code": reason, "error": messages.get(reason, reason)},
                                     202 if reason == "pending" else 410, {"Cache-Control": "no-store"})
            return self.json_out({"ok": True, "token": raw, "mcp": self.base_url() + "/mcp"}, headers={"Cache-Control": "no-store"})

        if path == "/api/members":
            if not self.authorised():
                return self.challenge()
            if STORE is None:
                return self.json_out({"enabled": False, "available": False, "members": [], "events": [],
                                      "error": "membership is off: set BENCH_MEMBERSHIP=1"})
            if not STORE.ok:
                return self.json_out({"enabled": True, "available": False, "members": [], "events": [], "error": STORE.error})
            return self.json_out({"enabled": True, "available": True, "members": STORE.list_members(),
                                  "events": STORE.events(50), "product": members.PRODUCT,
                                  "stripe": bool(billing_ready())}, headers={"Cache-Control": "no-store"})

        if path == "/api/codes":
            if not self.authorised():
                return self.challenge()
            doc = load_codes_doc()
            cats = sorted(set(["people"] + [str(c.get("category") or "general") for c in doc["codes"] if isinstance(c, dict)]))
            return self.json_out({
                "database": os.path.basename(CODES_DB),
                "exists": os.path.isfile(CODES_DB),
                "broken": doc.get("broken") or "",
                "codes": [dict(c, live=(not c.get("disabled") and not code_expired(c))) for c in doc["codes"] if isinstance(c, dict)],
                "env": [{"code": k, "groups": sorted(v)} for k, v in sorted(ENV_CODES.items())],
                "envRevoked": sorted(ENV_REVOKED),
                "revoked": doc["revoked"],
                "categories": cats,
                "nsfwGroup": NSFW_GROUP,
                "nsfwRealOverride": bool(SESSION_FLAGS.get(self.session_token(), {}).get("nsfwReal")),
            })

        if path == "/mcp":
            return self.json_out({"ok": False, "error": "MCP here is POST-only JSON-RPC. See /llms.txt."}, 405, {"Allow": "POST"})

        if path == "/api/agent" or path.startswith("/api/agent/"):
            return self.agent_get(path, query)

        rel = self.resolve_static(path)
        if not rel:
            return self.not_found()
        if STATIC[rel] == "auth" and not self.authorised():
            return self.challenge()
        return self.serve_file(rel)

    # ---------------- membership ----------------

    def bearer(self):
        header = self.headers.get("Authorization", "") or ""
        if header[:7].lower() == "bearer ":
            return header[7:].strip()
        return ""

    def paid_access(self, scope, route):
        """The one decision for every route a membership pays for.

        Returns None when the call may go ahead, or (http_status, code,
        message) when it may not. Membership never changes which packs a call
        can read: that stays with agent_scope(), so a member sees public packs
        (plus anything an unlock code opened), and only the owner sees private
        ones.
        """
        cached = getattr(self, "_paid", None)
        if cached is not None and cached[0] == scope:
            self._paid_route = route if cached[1] is None else None
            return cached[1]
        verdict = self._paid_verdict(scope, route)
        self._paid = (scope, verdict)
        self._paid_route = route if verdict is None else None
        return verdict

    def _paid_verdict(self, scope, route):
        if not MEMBERSHIP:
            return None
        if self.authorised():
            self._member = {"member_id": "owner", "credential_id": "owner"}
            return None
        link = membership_link(self.base_url())
        raw = self.bearer()
        if not raw:
            return (401, "membership_required",
                    "This needs a Prompt Bench membership. The website is free; the MCP tools and the agent API "
                    "are for members. Get one at " + link + " and send its token as Authorization: Bearer <token>.")
        if STORE is None or not STORE.ok:
            return (503, "membership_unavailable", "Membership checks are unavailable right now. Try again shortly.")
        who, reason = STORE.verify(raw, scope)
        if not who:
            addr = "token:" + self.client_addr()
            auth_failed(addr) if reason == "token_invalid" else None
            if reason == "token_invalid" and auth_blocked(addr):
                return (429, "rate_limited", "Too many unknown tokens from this address. Try again in ten minutes.")
            messages = {
                "token_invalid": "That token is not recognised. Check it, or get one at " + link + ".",
                "token_revoked": "That token has been revoked. Use your newer token, or see " + link + ".",
                "token_expired": "That token has expired. See " + link + ".",
                "token_scope": "That token cannot be used for this. See " + link + ".",
                "membership_inactive": "This membership is not active. See " + link + ".",
            }
            status = 403 if reason in ("membership_inactive", "token_scope") else 401
            STORE.record_use(None, None, route, reason)
            return (status, reason, messages.get(reason, "Not allowed. See " + link + "."))
        if not token_allowed(who["credential_id"]):
            STORE.record_use(who["member_id"], who["credential_id"], route, "rate_limited")
            return (429, "rate_limited", "Slow down: at most %d calls a minute per token." % TOKEN_RATE)
        self._member = who
        return None

    def paid_refusal(self, verdict):
        status, code, message = verdict
        headers = {"Retry-After": "60"} if status == 429 else {}
        if status == 401:
            headers["WWW-Authenticate"] = 'Bearer realm="prompt-bench", error="%s"' % (
                "invalid_token" if code != "membership_required" else "invalid_request")
        return self.json_out({"ok": False, "error": message, "code": code,
                              "membership": membership_link(self.base_url())}, status, headers)

    def note_use(self, route, outcome):
        who = getattr(self, "_member", None)
        if STORE is not None and STORE.ok and who and who.get("member_id") != "owner":
            STORE.record_use(who["member_id"], who["credential_id"], route, outcome)

    # ---------------- agent interface ----------------

    def agent_scope(self):
        """Signed in, the agent reads every pack; otherwise the public ones.

        The public scope is exactly what the shareable prompt is built from,
        so an unsigned agent can never reach a private cast.
        """
        if self.authorised():
            return "private"
        return "unlocked" if self.unlocked_groups() else "public"

    def run_agent(self, arguments, payload=None, flag="--recipe"):
        scope = self.agent_scope()
        headers = {"X-Pack-Scope": scope, "X-Pack-Version": pack_state_token()}
        if not ENGINE_SLOTS.acquire(timeout=ENGINE_WAIT):
            headers["Retry-After"] = "5"
            return None, headers, (503, "busy: too many prompts are being composed at once, try again in a few seconds")
        try:
            out, headers, err = self._run_agent(arguments, payload, flag, scope, headers)
        finally:
            ENGINE_SLOTS.release()
        # A paid call is counted once, when the engine actually produced
        # something. Discovery calls never reach here with a route set.
        route = getattr(self, "_paid_route", None)
        if route:
            self.note_use(route, "ok" if not err else "error")
            self._paid_route = None
        return out, headers, err

    def _run_agent(self, arguments, payload, flag, scope, headers):
        try:
            out = run_bench_cli(arguments, payload, public=(scope != "private"), payload_flag=flag,
                                groups=self.unlocked_groups() if scope == "unlocked" else None)
            return out, headers, None
        except RuntimeError as exc:
            return None, headers, (501, str(exc))
        except Exception as exc:
            return None, headers, (400, str(exc))

    def agent_get(self, path, query):
        if not agent_allowed(self.client_addr()):
            return self.json_out({"ok": False, "error": "slow down: at most %d agent requests a minute" % AGENT_RATE}, 429, {"Retry-After": "60"})
        what = path[len("/api/agent"):].strip("/") or "manifest"
        bench = (query.get("bench") or ["main"])[0]
        if bench not in ("main", "persona"):
            return self.json_out({"ok": False, "error": "bench is main or persona"}, 400)

        if what in PAID_AGENT_GET:
            verdict = self.paid_access("agent", "agent/" + what)
            if verdict:
                return self.paid_refusal(verdict)

        if what in ("capabilities", "model", "manifest"):
            scope = self.agent_scope()
            key = (what, bench, scope, ",".join(sorted(self.unlocked_groups())), pack_state_token(), self.base_url())
            cached = AGENT_CACHE.get(key)
            if cached is None:
                args = [what, "--bench", bench]
                if what == "manifest":
                    args += ["--base", self.base_url() + "/studio"]
                out, headers, err = self.run_agent(args)
                if err:
                    return self.json_out({"ok": False, "error": err[1]}, err[0], headers)
                if what == "manifest":
                    doc = json.loads(out)
                    doc["scope"] = scope
                    doc["endpoints"] = {
                        "guide": self.base_url() + "/llms.txt",
                        "openapi": self.base_url() + "/openapi.json",
                        "compose": self.base_url() + "/api/agent/compose",
                        "model": self.base_url() + "/api/agent/model?bench=" + bench,
                        "desk": self.base_url() + "/studio#agent",
                        "home": self.base_url() + "/home",
                    }
                    out = json.dumps(doc, ensure_ascii=False)
                with LOCK:
                    if len(AGENT_CACHE) > 64:
                        AGENT_CACHE.clear()
                    AGENT_CACHE[key] = out
                cached = out
            return self.raw_json(cached, headers={"X-Pack-Scope": key[2], "X-Pack-Version": key[4], "Cache-Control": "no-store"})

        if what == "compose":
            inp = {"bench": bench}
            one = lambda k: (query.get(k) or [""])[0]
            if one("brief"): inp["brief"] = one("brief")
            recipe = {}
            if one("recipe"):
                try:
                    raw = one("recipe")
                    raw += "=" * (-len(raw) % 4)
                    recipe = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
                except Exception:
                    return self.json_out({"ok": False, "error": "recipe must be base64url JSON, as carried after #recipe= in a Studio link"}, 400)
            if one("castJson"):
                try:
                    inp["cast"] = json.loads(one("castJson"))
                except Exception:
                    return self.json_out({"ok": False, "error": "castJson is not valid JSON"}, 400)
            elif query.get("cast"):
                inp["cast"] = [{"name": n} for n in query.get("cast") if n.strip()]
            if one("castCount"):
                try: recipe["castCount"] = max(0, int(one("castCount")))
                except ValueError: pass
            if one("master"): recipe["master"] = one("master")
            if query.get("module"): recipe["modules"] = (recipe.get("modules") or []) + query.get("module")
            if one("seed"):
                try: recipe["seed"] = int(one("seed"))
                except ValueError: pass
            if one("fill"): inp["fill"] = one("fill")
            if one("context"): inp["context"] = one("context")
            if recipe: inp["recipe"] = recipe
            if not inp.get("brief") and not recipe and not inp.get("cast"):
                return self.text_out(agent_guide(self.base_url()), 400)
            return self.agent_compose(inp, one("format") or "json", one("mode") or "prompt")

        return self.json_out({"ok": False, "error": "unknown agent route", "see": "/llms.txt"}, 404)

    def agent_compose(self, inp, fmt, mode):
        out, headers, err = self.run_agent(["compose", "--json", "--bench", inp.get("bench", "main"),
                                            "--base", self.base_url() + "/studio"], inp, flag="--input")
        if err:
            return self.json_out({"ok": False, "error": err[1]}, err[0], headers)
        if fmt == "text":
            doc = json.loads(out)
            text = doc.get(mode) or doc.get("prompt") or ""
            if doc.get("questions") and mode != "shareable":
                headers["X-Prompt-Ready"] = "yes" if doc.get("ready") else "no"
            return self.text_out(text + "\n", headers=headers)
        return self.raw_json(out, headers=headers)

    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, (400, "bad length")
        if length <= 0 or length > MAX_UPLOAD:
            return None, (413, "body must be between 1 byte and 512 KB")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")), None
        except Exception as exc:
            return None, (400, "request was not valid JSON: %s" % exc)

    def agent_post(self, path):
        if not agent_allowed(self.client_addr()):
            return self.json_out({"ok": False, "error": "slow down: at most %d agent requests a minute" % AGENT_RATE}, 429, {"Retry-After": "60"})
        what = path[len("/api/agent/"):].strip("/")
        if what not in PAID_AGENT_POST:
            return self.json_out({"ok": False, "error": "unknown agent route", "see": "/llms.txt"}, 404)
        verdict = self.paid_access("agent", "agent/" + what)
        if verdict:
            return self.paid_refusal(verdict)
        body, err = self.read_json_body()
        if err:
            return self.json_out({"ok": False, "error": err[1]}, err[0])
        if not isinstance(body, dict):
            return self.json_out({"ok": False, "error": "send a JSON object"}, 400)
        if "recipe" in body and not isinstance(body["recipe"], dict):
            return self.json_out({"ok": False, "error": "recipe must be a JSON object"}, 400)
        bench = str(body.get("bench") or (body.get("recipe") or {}).get("bench") or "main")
        if bench not in ("main", "persona"):
            return self.json_out({"ok": False, "error": "bench is main or persona"}, 400)

        if what == "compose":
            return self.agent_compose(body, "json", "prompt")
        if what == "suggest":
            # The brief goes on standard input, never on the command line, where a
            # brief starting with -- would be read as an option.
            inp = {"brief": str(body.get("brief") or "")}
            if isinstance(body.get("recipe"), dict):
                inp["recipe"] = body["recipe"]
            out, headers, e = self.run_agent(["suggest", "--bench", bench], inp, flag="--input")
            if e:
                return self.json_out({"ok": False, "error": e[1]}, e[0], headers)
            return self.raw_json(out, headers=headers)

        recipe = body.get("recipe")
        if not isinstance(recipe, dict):
            return self.json_out({"ok": False, "error": "send {\"recipe\": {...}} as the body"}, 400)
        arguments = [what, "--bench", bench]
        if what == "assemble":
            mode = str(body.get("mode") or "prompt")
            if mode not in ("prompt", "followup", "shareable"):
                return self.json_out({"ok": False, "error": "mode is prompt, followup or shareable"}, 400)
            arguments += ["--mode", mode, "--json"]
        if body.get("force"):
            arguments += ["--force"]
        out, headers, e = self.run_agent(arguments, recipe)
        if e:
            return self.json_out({"ok": False, "error": e[1]}, e[0], headers)
        return self.raw_json(out, headers=headers)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/agent/"):
            return self.agent_post(path)

        if path == "/mcp":
            return self.mcp_post()

        if path == "/api/unlock":
            return self.unlock_post()
        if path == "/api/unlock/forget":
            self._set_cookie = UNLOCK_COOKIE + "=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
            return self.json_out({"ok": True, "unlocked": []})

        if path in ("/api/codes/save", "/api/codes/delete", "/api/unlock/revoke", "/api/admin/nsfw-override"):
            return self.admin_codes_post(path)

        if path.startswith("/api/members/"):
            return self.admin_members_post(path)

        if path == "/api/membership/rotate":
            if STORE is None or not STORE.ok:
                return self.json_out({"ok": False, "code": "membership_unavailable"}, 503)
            cred = STORE.credential_for(self.bearer())
            if not cred:
                auth_failed("token:" + self.client_addr())
                return self.json_out({"ok": False, "code": "token_invalid", "error": "that token is not recognised"}, 401)
            cid, raw = STORE.rotate_token(cred["credential_id"])
            return self.json_out({"ok": True, "token": raw, "credential": cid,
                                  "note": "The old token stopped working just now. This one is shown once."},
                                 headers={"Cache-Control": "no-store"})

        if path == "/api/stripe/webhook":
            return self.stripe_webhook()

        if path == "/api/logout":
            end_session(self.session_token())
            self._set_cookie = SESSION_COOKIE + "=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
            return self.json_out({"ok": True})

        if path not in ("/api/upload", "/api/remove", "/api/import-github"):
            return self.not_found()
        if not self.authorised():
            return self.challenge()
        if not self.same_origin_write():
            return self.json_out({"ok": False, "error": "writes must come from this site's admin page, as JSON"}, 403)
        payload, err = self.read_json_body()
        if err:
            return self.json_out({"ok": False, "error": err[1]}, err[0])
        if not isinstance(payload, dict):
            return self.json_out({"ok": False, "error": "expected a JSON object"}, 400)

        # A write carrying a stamp is refused when the packs have moved on, so
        # two administrators cannot overwrite each other without noticing.
        sent = payload.get("packVersion")
        if sent and sent != pack_state_token():
            return self.json_out({
                "ok": False, "stale": True,
                "error": "somebody else has installed or removed packs since this page was loaded. "
                         "Reload it and try again, so their change is not overwritten."
            }, 409)

        if path == "/api/import-github":
            try:
                result = import_github_repository(payload.get("url"), payload.get("token"),
                                                  payload.get("bench") or "main")
                AGENT_CACHE.clear()
                return self.json_out(result)
            except urllib.error.HTTPError as exc:
                used = bool((payload.get("token") or os.environ.get("GITHUB_TOKEN", "")).strip())
                msg = github_error_message(exc, used)
                sys.stderr.write("github import refused (%s): %s\n" % (exc.code, msg))
                return self.json_out({"ok": False, "error": msg}, 400)
            except urllib.error.URLError as exc:
                sys.stderr.write("github import could not reach GitHub: %s\n" % exc.reason)
                return self.json_out({"ok": False, "error": "could not reach GitHub: %s" % exc.reason}, 502)
            except (ValueError, json.JSONDecodeError) as exc:
                sys.stderr.write("github import failed: %s\n" % exc)
                return self.json_out({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:
                sys.stderr.write("github import error: %s\n" % exc)
                return self.json_out({"ok": False, "error": "GitHub import failed: %s" % exc}, 500)

        target = (persona_upload_path(payload.get("name"))
                  if (payload.get("bench") == "persona") else safe_upload_path(payload.get("name")))
        if not target:
            return self.json_out({"ok": False, "error": "a usable filename is required"}, 400)

        if path == "/api/remove":
            if not os.path.isfile(target):
                return self.json_out({"ok": False, "error": "no such uploaded pack"}, 404)
            try:
                os.remove(target)
            except OSError as exc:
                return self.json_out({"ok": False, "error": str(exc)}, 500)
            AGENT_CACHE.clear()
            return self.json_out({"ok": True, "removed": os.path.basename(target),
                                  "packVersion": pack_state_token()})

        pack = payload.get("pack")
        if not isinstance(pack, dict):
            return self.json_out({"ok": False, "error": "pack must be a JSON object"}, 400)
        if not is_prompt_bench_pack(pack):
            return self.json_out({"ok": False, "error": "that file contains none of the recognised pack keys"}, 400)

        try:
            write_pack_file(target, pack)
        except OSError as exc:
            return self.json_out({"ok": False, "error": "could not write: %s" % exc}, 500)
        AGENT_CACHE.clear()
        return self.json_out({"ok": True, "saved": os.path.basename(target),
                              "packVersion": pack_state_token()})

    # ---------------- unlock codes ----------------

    def unlock_post(self):
        """Trade a code for a signed cookie naming the groups it opens.

        Wrong codes count against the address the same way wrong passwords do:
        five in ten minutes and it waits. With 36 characters to the position,
        a six character code is about two billion possibilities, which that
        limit puts far out of reach of guessing.
        """
        addr = "unlock:" + self.client_addr()
        if auth_blocked(addr):
            return self.json_out({"ok": False, "error": "Too many wrong codes from here. Try again in ten minutes."},
                                 429, {"Retry-After": str(AUTH_WINDOW)})
        codes = live_codes()
        if not codes:
            return self.json_out({"ok": False, "error": "This server has no unlock codes set up."}, 404)
        if (self.headers.get("Content-Type", "") or "").split(";")[0].strip().lower() != "application/json":
            return self.json_out({"ok": False, "error": "send {\"code\": \"...\"} as JSON"}, 400)
        body, err = self.read_json_body()
        if err or not isinstance(body, dict):
            return self.json_out({"ok": False, "error": (err or (400, "send a JSON object"))[1]}, 400)
        code = re.sub(r"[^A-Za-z0-9]", "", str(body.get("code") or "")).upper()
        groups = set()
        for known, entry in codes.items():
            if hmac.compare_digest(code.encode(), known.encode()):
                groups |= entry["groups"]
        if not groups:
            auth_failed(addr)
            time.sleep(0.4)
            return self.json_out({"ok": False, "error": "That code does not open anything."}, 403)
        granted = set(groups)
        # A browser that already holds a live unlock keeps its id, so a second
        # code adds to the same identity instead of starting a new one.
        held, rid = self.unlock_doc()
        groups |= held
        rid = rid or secrets.token_hex(4)
        secure = "; Secure" if self.scheme() == "https" else ""
        self._set_cookie = (UNLOCK_COOKIE + "=" + sign_unlock(groups, rid) + "; Path=/; Max-Age=" + str(UNLOCK_TTL)
                            + "; HttpOnly; SameSite=Lax" + secure)
        names = [p["data"].get("pack") or p["path"] for p in all_packs() if is_gated(p) and visible_to(p, groups)]
        log_redemption({"id": rid, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "code": code,
                        "granted": sorted(granted), "groups": sorted(groups), "packs": names,
                        "ip": self.client_addr(), "agent": (self.headers.get("User-Agent") or "")[:200]})
        AGENT_CACHE.clear()
        return self.json_out({"ok": True, "unlocked": sorted(groups), "packs": names, "id": rid})

    # ---------------- the codes database, from the admin page ----------------

    def admin_codes_post(self, path):
        if not self.authorised():
            return self.challenge()
        if not self.same_origin_write():
            return self.json_out({"ok": False, "error": "writes must come from this site's admin page, as JSON"}, 403)
        body, err = self.read_json_body()
        if err:
            return self.json_out({"ok": False, "error": err[1]}, err[0])
        if not isinstance(body, dict):
            return self.json_out({"ok": False, "error": "expected a JSON object"}, 400)

        if path == "/api/admin/nsfw-override":
            token = self.session_token()
            if not valid_session(token):
                return self.json_out({"ok": False, "error": "sign in on the admin page first; the switch belongs to a session"}, 400)
            on = bool(body.get("on"))
            with LOCK:
                SESSION_FLAGS.setdefault(token, {})["nsfwReal"] = on
            sys.stderr.write("admin NSFW real-person override %s\n" % ("on" if on else "off"))
            return self.json_out({"ok": True, "nsfwRealOverride": on})

        try:
            # A shallow copy with fresh lists: other top-level keys (notes someone
            # wrote into the file by hand) survive the save untouched.
            doc = dict(load_codes_doc())
            doc["codes"], doc["revoked"] = list(doc["codes"]), list(doc["revoked"])
            if path == "/api/codes/save":
                # "was" names the entry being edited. Without it this is a new
                # code, and one that already exists is refused, not replaced.
                was = clean_code(body.get("was"))
                old = next((c for c in doc["codes"] if isinstance(c, dict) and clean_code(c.get("code")) == was), None) if was else None
                if was and old is None:
                    return self.json_out({"ok": False, "error": "the code being edited is no longer in the database; reload the page"}, 409)
                entry = validate_code_entry(body, old)
                clash = next((c for c in doc["codes"] if isinstance(c, dict) and c is not old
                              and clean_code(c.get("code")) == entry["code"]), None)
                if clash:
                    return self.json_out({"ok": False, "error": "that code is already in the database"}, 409)
                doc["codes"] = [c for c in doc["codes"] if c is not old] + [entry]
                doc["codes"].sort(key=lambda c: (str(c.get("category", "")), str(c.get("code", ""))))
                save_codes_doc(doc)
                result = {"ok": True, "saved": entry}
            elif path == "/api/codes/delete":
                code = clean_code(body.get("code"))
                keep = [c for c in doc["codes"] if not (isinstance(c, dict) and clean_code(c.get("code")) == code)]
                if len(keep) == len(doc["codes"]):
                    return self.json_out({"ok": False, "error": "no such code in the database"}, 404)
                doc["codes"] = keep
                save_codes_doc(doc)
                result = {"ok": True, "deleted": code}
            else:  # /api/unlock/revoke
                rid = re.sub(r"[^a-f0-9]", "", str(body.get("id") or "").lower())[:16]
                if not rid:
                    return self.json_out({"ok": False, "error": "which redemption id?"}, 400)
                if body.get("undo"):
                    if rid in ENV_REVOKED:
                        return self.json_out({"ok": False, "error": "that id is revoked in .env (BENCH_UNLOCK_REVOKED); remove it there"}, 409)
                    doc["revoked"] = [r for r in doc["revoked"] if str((r.get("id") if isinstance(r, dict) else r) or "").lower() != rid]
                else:
                    if rid not in revoked_ids():
                        doc["revoked"].append({"id": rid, "at": now_iso(), "note": str(body.get("note") or "")[:200]})
                save_codes_doc(doc)
                result = {"ok": True, "id": rid, "revoked": not body.get("undo")}
        except ValueError as exc:
            return self.json_out({"ok": False, "error": str(exc)}, 400)
        except OSError as exc:
            return self.json_out({"ok": False, "error": "could not write the codes database: %s" % exc}, 500)
        AGENT_CACHE.clear()
        return self.json_out(result)

    # ---------------- Stripe ----------------

    def stripe_webhook(self):
        """Stripe events. The body is verified as raw bytes before anything is
        parsed or changed, stored by event id before it is acted on, and a
        retried delivery of a processed event changes nothing."""
        if STORE is None or not STORE.ok or not billing.ready():
            return self.json_out({"ok": False, "error": "billing is not configured"}, 503)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.json_out({"ok": False, "error": "bad length"}, 400)
        if length <= 0 or length > MAX_UPLOAD:
            return self.json_out({"ok": False, "error": "bad length"}, 413)
        payload = self.rfile.read(length)
        try:
            event = billing.verify(payload, self.headers.get("Stripe-Signature", ""))
        except (billing.BadSignature, ValueError) as exc:
            sys.stderr.write("stripe webhook refused: %s\n" % exc)
            return self.json_out({"ok": False, "error": "signature not accepted"}, 400)
        if not STORE.begin_event(billing.PROVIDER, event["id"], event["type"]):
            return self.json_out({"ok": True, "duplicate": True})
        try:
            status, detail = billing.handle(STORE, event)
        except Exception as exc:
            STORE.finish_event(billing.PROVIDER, event["id"], "failed", str(exc))
            sys.stderr.write("stripe event %s failed: %s\n" % (event["id"], exc))
            return self.json_out({"ok": False, "error": "could not apply the event; Stripe will retry"}, 500)
        STORE.finish_event(billing.PROVIDER, event["id"], status, detail)
        sys.stderr.write("stripe event %s %s: %s\n" % (event["type"], status, detail))
        return self.json_out({"ok": True, "status": status})

    # ---------------- members, from the admin page ----------------

    def admin_members_post(self, path):
        if not self.authorised():
            return self.challenge()
        if not self.same_origin_write():
            return self.json_out({"ok": False, "error": "writes must come from this site's admin page, as JSON"}, 403)
        if STORE is None or not STORE.ok:
            return self.json_out({"ok": False, "error": "membership is off or its database is unavailable"}, 503)
        body, err = self.read_json_body()
        if err:
            return self.json_out({"ok": False, "error": err[1]}, err[0])
        if not isinstance(body, dict):
            return self.json_out({"ok": False, "error": "expected a JSON object"}, 400)
        what = path[len("/api/members/"):]
        text = lambda k, n: str(body.get(k) or "").strip()[:n]
        date = lambda k: (text(k, 10) + "T23:59:59Z") if re.match(r"^\d{4}-\d{2}-\d{2}$", text(k, 10)) else None
        try:
            if what == "create":
                mid = STORE.create_member(text("name", 120), text("email", 200), text("notes", 500))
                out = {"ok": True, "member": mid}
                if body.get("grant"):
                    out["entitlement"] = STORE.grant(mid, source="manual", ends_at=date("ends"), reason="granted by the owner")
                if body.get("token"):
                    out["credential"], out["token"] = STORE.issue_token(mid, text("label", 80) or "issued by the owner")
                return self.json_out(out, headers={"Cache-Control": "no-store"})
            if what == "update":
                STORE.update_member(text("member", 40), name=text("name", 120), email=text("email", 200), notes=text("notes", 500))
                return self.json_out({"ok": True})
            if what == "grant":
                if not STORE.member(text("member", 40)):
                    return self.json_out({"ok": False, "error": "no such member"}, 404)
                eid = STORE.grant(text("member", 40), source="manual", ends_at=date("ends"), reason="granted by the owner")
                return self.json_out({"ok": True, "entitlement": eid})
            if what == "entitlement":
                kw = {}
                if body.get("status") in ("active", "revoked"):
                    kw["status"] = body["status"]
                if "disputed" in body:
                    kw["disputed"] = bool(body["disputed"])
                if "ends" in body:
                    kw["ends_at"] = date("ends") or ""
                if body.get("reason"):
                    kw["reason"] = text("reason", 200)
                STORE.set_entitlement(text("entitlement", 40), **kw)
                return self.json_out({"ok": True})
            if what == "token":
                cid, raw = STORE.issue_token(text("member", 40), text("label", 80) or "issued by the owner")
                return self.json_out({"ok": True, "credential": cid, "token": raw}, headers={"Cache-Control": "no-store"})
            if what == "revoke-token":
                return self.json_out({"ok": STORE.revoke_token(text("credential", 40))})
        except KeyError as exc:
            return self.json_out({"ok": False, "error": str(exc).strip("'")}, 404)
        except ValueError as exc:
            return self.json_out({"ok": False, "error": str(exc)}, 400)
        return self.json_out({"ok": False, "error": "unknown members route"}, 404)

    # ---------------- MCP ----------------

    MCP_TOOLS = [
        {"name": "compose_prompt",
         "description": "Turn a client's own words into a finished image prompt that leaves the image model nothing to invent. "
                        "Returns the prompt, a shareable version with every real person removed, the gaps still open and ready-to-send questions. "
                        "Explicit cast and recipe always win; the brief only fills what they leave empty.",
         "inputSchema": {"type": "object", "properties": {
             "brief": {"type": "string", "description": "The client's request, untouched."},
             "bench": {"type": "string", "enum": ["main", "persona"], "description": "main: a scene with up to five characters. persona: one portrait subject."},
             "cast": {"type": "array", "description": "The whole cast, in order.", "items": {"type": "object", "properties": {
                 "name": {"type": "string"}, "kind": {"type": "string", "enum": ["person", "animal"]},
                 "marker": {"type": "string", "description": "The one thing always present that makes them recognisable."},
                 "looks": {"type": "string"}, "wears": {"type": "string"}, "manner": {"type": "string"},
                 "photo": {"type": "boolean", "description": "true if a reference photo of them will be attached."}}}},
             "recipe": {"type": "object", "description": "Explicit choices: master, modules (exact wording), castCount, dials, fields, seed."},
             "context": {"type": "string", "description": "Who these people are to each other."},
             "fill": {"type": "string", "enum": ["empty", "none"]},
             "mode": {"type": "string", "enum": ["prompt", "shareable", "followup"], "description": "Which text to put first in the reply."}},
             "required": ["brief"]}},
        {"name": "suggest_from_brief",
         "description": "Read a brief and propose a master, cast size, modules and dials, without building a prompt.",
         "inputSchema": {"type": "object", "properties": {"brief": {"type": "string"}, "bench": {"type": "string", "enum": ["main", "persona"]}}, "required": ["brief"]}},
        {"name": "list_gaps",
         "description": "What a recipe still leaves open, as questions with where each answer goes.",
         "inputSchema": {"type": "object", "properties": {"recipe": {"type": "object"}, "bench": {"type": "string", "enum": ["main", "persona"]}}, "required": ["recipe"]}},
        {"name": "get_manifest",
         "description": "What this Prompt Bench offers: masters, categories, cast fields, dials, text fields and the rules.",
         "inputSchema": {"type": "object", "properties": {"bench": {"type": "string", "enum": ["main", "persona"]}}}},
        {"name": "list_modules",
         "description": "The exact wording of every module in one category, to choose from by wording.",
         "inputSchema": {"type": "object", "properties": {"category": {"type": "string", "description": "e.g. MEDIUM, PALETTE, SCENE"}, "bench": {"type": "string", "enum": ["main", "persona"]}}, "required": ["category"]}},
    ]

    def mcp_post(self):
        """A small Model Context Protocol server over plain HTTP POST.

        Stateless JSON-RPC 2.0: every request is answered in one JSON response,
        which the streamable HTTP transport allows. The tools run the same CLI
        as /api/agent, with the same scope and the same rate limit.
        """
        if not agent_allowed(self.client_addr()):
            return self.json_out({"jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "rate limited"}}, 429)
        body, err = self.read_json_body()
        if err:
            return self.json_out({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": err[1]}}, 400)
        batch = body if isinstance(body, list) else [body]
        # Each tool call starts the engine, so a batch may not smuggle past the
        # rate limit: it is capped, and every call after the first is metered.
        if len(batch) > MCP_BATCH:
            return self.json_out({"jsonrpc": "2.0", "id": None,
                                  "error": {"code": -32600, "message": "at most %d messages in a batch" % MCP_BATCH}}, 400)
        replies = [r for r in (self.mcp_one(m) for m in batch) if r is not None]
        if not replies:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return self.json_out(replies if isinstance(body, list) else replies[0])

    def mcp_one(self, msg):
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "not JSON-RPC 2.0"}}
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:
            return None                      # a notification, such as notifications/initialized
        if not isinstance(params, dict):
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "params must be an object"}}
        ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}
        if method == "initialize":
            return ok({"protocolVersion": params.get("protocolVersion") or "2025-06-18",
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "prompt-bench", "title": "Prompt Bench", "version": "3"},
                       "instructions": "Call compose_prompt with the client's words and whatever cast you know. "
                                       "If the result is not ready, ask the client its questions and call again with the answers."})
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": self.MCP_TOOLS})
        if method != "tools/call":
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "unknown method " + str(method)}}
        name, args = params.get("name"), params.get("arguments") or {}
        if not isinstance(args, dict):
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "arguments must be an object"}}
        if getattr(self, "_mcp_calls", 0) and not agent_allowed(self.client_addr()):
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": "rate limited"}}
        self._mcp_calls = getattr(self, "_mcp_calls", 0) + 1
        bench = args.get("bench") if args.get("bench") in ("main", "persona") else "main"
        def tool_result(text, structured=None, error=False):
            r = {"content": [{"type": "text", "text": text}], "isError": error}
            if structured is not None:
                r["structuredContent"] = structured
            return ok(r)
        # Listing the tools is free; using one is what a membership pays for.
        # A refusal is a tool result, not a protocol error, so the client shows
        # the person the message and the link rather than a broken connection.
        verdict = self.paid_access("mcp", "mcp/" + str(name))
        if verdict:
            return tool_result(verdict[2], {"code": verdict[1], "membership": membership_link(self.base_url())},
                               error=True)
        self._mcp_tool = str(name)
        if name == "compose_prompt":
            inp = {k: args[k] for k in ("brief", "cast", "recipe", "context", "fill") if k in args}
            inp["bench"] = bench
            out, _, e = self.run_agent(["compose", "--json", "--bench", bench, "--base", self.base_url() + "/studio"], inp, flag="--input")
            if e:
                return tool_result(e[1], error=True)
            doc = json.loads(out)
            first = args.get("mode") if args.get("mode") in ("prompt", "shareable", "followup") else "prompt"
            text = ("READY" if doc.get("ready") else "NOT READY: answer these first") + "\n\n"
            if doc.get("questions"):
                text += "Questions for the client:\n" + doc["questions"] + "\n\n"
            text += first.upper() + ":\n" + doc.get(first, "")
            return tool_result(text, {k: doc.get(k) for k in ("ready", "prompt", "shareable", "followup", "gaps", "questions", "decisions", "recipe", "link")})
        if name == "suggest_from_brief":
            out, _, e = self.run_agent(["suggest", "--bench", bench], {"brief": str(args.get("brief") or "")}, flag="--input")
            return tool_result(e[1], error=True) if e else tool_result(out, json.loads(out))
        if name == "list_gaps":
            out, _, e = self.run_agent(["gaps", "--bench", bench], args.get("recipe") or {})
            return tool_result(e[1], error=True) if e else tool_result(json.loads(out).get("questions") or "Nothing open.", json.loads(out))
        if name == "get_manifest":
            out, _, e = self.run_agent(["manifest", "--bench", bench])
            return tool_result(e[1], error=True) if e else tool_result(out, json.loads(out))
        if name == "list_modules":
            out, _, e = self.run_agent(["model", "--bench", bench, "--category", str(args.get("category") or "").upper()])
            if e:
                return tool_result(e[1], error=True)
            cat = json.loads(out)
            lines = ["%s: %s" % (cat.get("label"), cat.get("note", ""))] + ["- " + it["t"] for it in cat.get("items", [])]
            return tool_result("\n".join(lines), cat)
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool " + str(name)}}

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        # Every response passes through here, static files included, so this is
        # where a session granted during this request goes out.
        pending = getattr(self, "_set_cookie", "")
        if pending:
            self._set_cookie = ""
            self.send_header("Set-Cookie", pending)
        super().end_headers()

    def log_message(self, fmt, *args):
        # The request line can carry a brief in its query string
        # (/api/agent/compose?brief=...), which is a customer's own words.
        # Log the path only. Headers, and so tokens, are never logged.
        line = re.sub(r"\?[^ \"]*", "?…", fmt % args)
        sys.stderr.write("%s %s\n" % (self.client_addr(), line))


if __name__ == "__main__":
    os.chdir(ROOT)
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write("Prompt Bench serving on port %d\n" % PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
