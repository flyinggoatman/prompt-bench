#!/usr/bin/env python3
# Prompt Bench server. Standard library only.
#
# Public, no authentication:
#   GET  /                 the app
#   GET  /api/packs        every pack NOT marked private, main bench unless
#                          ?bench=persona asks otherwise
#   GET  /healthz
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

ROOT = os.path.abspath(os.path.dirname(__file__))
PACKS = os.path.join(ROOT, "packs")
UPLOADS = os.path.join(ROOT, "uploads")
PORT = int(os.environ.get("BENCH_PORT", "8080"))
USER = os.environ.get("BENCH_USER", "")
PASS = os.environ.get("BENCH_PASS", "")
MAX_UPLOAD = 512 * 1024
MAX_GITHUB_ARCHIVE = 8 * 1024 * 1024
MAX_GITHUB_JSON_FILES = 250
MAX_GITHUB_PACKS = 150
SAFE = re.compile(r"[^A-Za-z0-9._-]")
KNOWN_PACK_KEYS = (
    "shared", "masters", "people", "categories", "wording", "settings",
    "castFields", "discipline", "dials", "variation", "fields"
)

if not USER or not PASS:
    sys.stderr.write("BENCH_USER and BENCH_PASS must both be set. Refusing to start.\n")
    sys.exit(2)

EXPECTED = "Basic " + base64.b64encode((USER + ":" + PASS).encode("utf-8")).decode("ascii")


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


def run_bench_cli(arguments, recipe=None):
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
        arguments = arguments + ["--recipe", "-"]
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


# Sessions live in memory only. A restart signs everybody out, which is the
# right trade for a single small server: nothing to persist, nothing to leak,
# and the owner signs in again on the admin page.
SESSION_COOKIE = "bench_session"
SESSION_TTL = 12 * 60 * 60
SESSIONS = {}


def new_session():
    prune_sessions()
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = time.time() + SESSION_TTL
    return token


def valid_session(token):
    if not token:
        return False
    expires = SESSIONS.get(token)
    if expires is None:
        return False
    if expires < time.time():
        SESSIONS.pop(token, None)
        return False
    return True


def prune_sessions():
    now = time.time()
    for token in [t for t, exp in SESSIONS.items() if exp < now]:
        SESSIONS.pop(token, None)


def packs_for_bench(entries, bench):
    """What one bench is served. Its own packs and anything marked for both.

    A bench never receives the other's packs. Borrowing a category from the
    other bench happens in the page, on packs it already holds, so nothing has
    to be served twice.
    """
    if bench not in ("main", "persona"):
        return entries
    return [e for e in entries if pack_bench(e) in (bench, "both")]


def is_private(entry):
    d = entry.get("data")
    return bool(isinstance(d, dict) and d.get("private"))


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
    try:
        u = urllib.parse.urlparse((value or "").strip())
    except Exception:
        return None
    if u.scheme.lower() != "https" or (u.hostname or "").lower() != "github.com":
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
    return owner, repo


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
        raise ValueError("use a repository link beginning https://github.com/owner/repository")
    owner, repo = parsed
    token = (supplied_token or os.environ.get("GITHUB_TOKEN", "")).strip() or None

    branch = github_repo_info(owner, repo, token)
    archive = github_zipball(owner, repo, branch, token)

    installed = []
    skipped = []
    json_seen = 0
    pack_seen = 0

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile:
        raise ValueError("GitHub did not return a readable repository archive")

    with zf:
        for entry in zf.infolist():
            if entry.is_dir() or not entry.filename.lower().endswith(".json"):
                continue
            # A bench imports only what belongs to it. The persona bench takes
            # the persona-packs subtree of the repository and nothing else; the
            # main bench takes everything but that subtree.
            in_persona = "persona-packs/" in entry.filename.replace("\\", "/")
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

            bits = entry.filename.replace("\\", "/").split("/", 1)
            rel = bits[1] if len(bits) > 1 else bits[0]
            if not rel or any(p in ("..", "") for p in rel.split("/")):
                skipped.append({"path": rel or entry.filename, "reason": "unsafe path"})
                continue

            try:
                raw = zf.read(entry)
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
        raise ValueError("no valid Prompt Bench pack JSON files were found in that repository")

    return {
        "ok": True,
        "repository": "%s/%s" % (owner, repo),
        "branch": branch,
        "installed": installed,
        "skipped": skipped,
        "used_token": bool(token),
    }


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = "PromptBench/2"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_PUT(self): self.send_error(405)
    def do_DELETE(self): self.send_error(405)
    def do_PATCH(self): self.send_error(405)

    def authorised(self):
        """Signed in, by password on this request or by a session from an earlier one.

        Basic Auth alone is not enough. A browser sends those credentials back
        to the path it was challenged on and its children, so a sign in at
        /admin does not reach /api/packs, and the bench page had no way to know
        the person at the keyboard is the owner. A session cookie issued on a
        successful sign in closes that gap without a second password box.
        """
        header = self.headers.get("Authorization", "")
        if header and hmac.compare_digest(header, EXPECTED):
            self.grant_session()
            return True
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
        proto = (self.headers.get("X-Forwarded-Proto", "") or "").split(",")[0].strip().lower()
        secure = "; Secure" if proto == "https" else ""
        self._set_cookie = (SESSION_COOKIE + "=" + token + "; Path=/; Max-Age=" + str(SESSION_TTL)
                            + "; HttpOnly; SameSite=Strict" + secure)

    def challenge(self):
        body = b"Unauthorised\n"
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Prompt Bench admin", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def json_out(self, obj, code=200, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/admin") and not self.authorised():
            return self.challenge()
        return super().do_HEAD()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

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
            if want == "auto":
                if not signed_in:
                    packs = [p for p in packs if not is_private(p)]
            elif want:
                if not signed_in:
                    return self.challenge()
            else:
                packs = [p for p in packs if not is_private(p)]
            # A caller that names no bench gets the main bench rather than
            # both merged. Serving both hands the page two benches' settings
            # at once, and the last one read wins: the persona masters cap the
            # cast at one, so a main bench built from an unscoped list offers
            # a single person. Defaulting here matches /api/agent/ and keeps a
            # stale page honest instead of quietly wrong.
            bench = (query.get("bench") or ["main"])[0]
            packs = packs_for_bench(packs, bench)
            return self.json_out(packs, headers={
                "X-Pack-Version": pack_state_token(),
                "X-Pack-Scope": "private" if (signed_in and want) else "public",
            })

        # Cheap enough to poll: a page uses it to notice that somebody has
        # installed packs since it loaded, and offers a reload rather than
        # reaching in and changing what is on screen.
        if path == "/api/packs/version":
            return self.json_out({"version": pack_state_token()})

        # The agent interface reads every pack, private ones included, so it
        # sits behind the same password as the admin page rather than being
        # open the way the public pack list is.
        if path.startswith("/api/agent/"):
            if not self.authorised():
                return self.challenge()
            bench = (query.get("bench") or ["main"])[0]
            what = path[len("/api/agent/"):].strip("/")
            if what not in ("capabilities", "model", "offered"):
                return self.json_out({"ok": False, "error": "unknown agent route"}, 404)
            if what == "offered":
                return self.json_out({"ok": False,
                                      "error": "offered needs a recipe, so POST it to this route"}, 400)
            try:
                return self.raw_json(run_bench_cli([what, "--bench", bench]))
            except RuntimeError as exc:
                return self.json_out({"ok": False, "error": str(exc)}, 501)
            except Exception as exc:
                return self.json_out({"ok": False, "error": str(exc)}, 400)

        if path in ("/admin", "/admin/", "/admin.html"):
            if not self.authorised():
                return self.challenge()
            self.path = "/admin.html"
            return super().do_GET()

        if path in ("/admin-persona", "/admin-persona/", "/admin-persona.html"):
            if not self.authorised():
                return self.challenge()
            self.path = "/admin-persona.html"
            return super().do_GET()

        if path in ("/persona", "/persona/"):
            self.path = "/persona-bench.html"
            return super().do_GET()

        if path == "/":
            self.path = "/prompt-bench.html"
        elif path == "/prompt-bench-offline.html":
            if not self.authorised():
                return self.challenge()
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/agent/"):
            if not self.authorised():
                return self.challenge()
            what = path[len("/api/agent/"):].strip("/")
            if what not in ("assemble", "offered", "recipe"):
                return self.json_out({"ok": False, "error": "unknown agent route"}, 404)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.json_out({"ok": False, "error": "bad length"}, 400)
            if length <= 0 or length > MAX_UPLOAD:
                return self.json_out({"ok": False, "error": "body must be between 1 byte and 512 KB"}, 413)
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception as exc:
                return self.json_out({"ok": False, "error": "request was not valid JSON: %s" % exc}, 400)
            recipe = body.get("recipe") if isinstance(body, dict) else None
            if not isinstance(recipe, dict):
                return self.json_out({"ok": False, "error": "send {\"recipe\": {...}} as the body"}, 400)
            arguments = [what]
            if body.get("bench"):
                arguments += ["--bench", str(body["bench"])]
            if what == "assemble":
                arguments += ["--mode", str(body.get("mode") or "prompt"), "--json"]
            if body.get("force"):
                arguments += ["--force"]
            try:
                return self.raw_json(run_bench_cli(arguments, recipe))
            except RuntimeError as exc:
                return self.json_out({"ok": False, "error": str(exc)}, 501)
            except Exception as exc:
                return self.json_out({"ok": False, "error": str(exc)}, 400)

        if path not in ("/api/upload", "/api/remove", "/api/import-github"):
            return self.send_error(404)
        if not self.authorised():
            return self.challenge()
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.json_out({"ok": False, "error": "bad length"}, 400)
        if length <= 0 or length > MAX_UPLOAD:
            return self.json_out({"ok": False, "error": "body must be between 1 byte and 512 KB"}, 413)
        raw = self.rfile.read(length)

        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            return self.json_out({"ok": False, "error": "request was not valid JSON: %s" % exc}, 400)
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
                return self.json_out(result)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403, 404):
                    return self.json_out({
                        "ok": False,
                        "error": "GitHub could not access that repository. If it is private, configure GITHUB_TOKEN on the server or use the one-use token box."
                    }, 400)
                return self.json_out({"ok": False, "error": "GitHub returned HTTP %d" % exc.code}, 400)
            except urllib.error.URLError as exc:
                return self.json_out({"ok": False, "error": "could not reach GitHub: %s" % exc.reason}, 502)
            except (ValueError, json.JSONDecodeError) as exc:
                return self.json_out({"ok": False, "error": str(exc)}, 400)
            except Exception as exc:
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
        return self.json_out({"ok": True, "saved": os.path.basename(target),
                              "packVersion": pack_state_token()})

    def raw_json(self, text, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        # Every response passes through here, static files included, so this is
        # where a session granted during this request goes out.
        pending = getattr(self, "_set_cookie", "")
        if pending:
            self._set_cookie = ""
            self.send_header("Set-Cookie", pending)
        super().end_headers()

    def translate_path(self, path):
        path = urllib.parse.urlparse(path).path
        path = posixpath.normpath(urllib.parse.unquote(path))
        parts = [p for p in path.split("/") if p and p not in (".", "..")]
        if any(p.startswith(".") for p in parts):
            return os.path.join(ROOT, "__denied__")
        return os.path.join(ROOT, *parts)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    os.chdir(ROOT)
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write("Prompt Bench serving on port %d\n" % PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
