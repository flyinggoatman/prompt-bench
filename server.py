#!/usr/bin/env python3
# Prompt Bench server. Standard library only.
#
# Public, no authentication:
#   GET  /                 the app
#   GET  /api/packs        every pack NOT marked private
#   GET  /healthz
#
# Authenticated with HTTP Basic (BENCH_USER / BENCH_PASS):
#   GET  /admin            the management page
#   GET  /api/packs?all=1  every pack including private ones
#   POST /api/upload       add a JSON pack to uploads/
#   POST /api/remove       delete a pack from uploads/
#
# Writes are confined to the uploads directory, accept only JSON that parses,
# are size capped, and use a sanitised filename. There is no shell, no script
# execution, and nothing outside the app directory is reachable.

import base64
import http.server
import json
import os
import posixpath
import re
import sys
import urllib.parse

ROOT = os.path.abspath(os.path.dirname(__file__))
PACKS = os.path.join(ROOT, "packs")
UPLOADS = os.path.join(ROOT, "uploads")
PORT = int(os.environ.get("BENCH_PORT", "8080"))
USER = os.environ.get("BENCH_USER", "")
PASS = os.environ.get("BENCH_PASS", "")
MAX_UPLOAD = 512 * 1024
SAFE = re.compile(r"[^A-Za-z0-9._-]")

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


def all_packs():
    return read_dir(PACKS, "packs") + read_dir(UPLOADS, "uploads")


def is_private(entry):
    d = entry.get("data")
    return bool(isinstance(d, dict) and d.get("private"))


def safe_upload_path(name):
    name = os.path.basename(name or "")
    name = SAFE.sub("-", name).strip("-.")
    if not name:
        return None
    if not name.lower().endswith(".json"):
        name += ".json"
    return os.path.join(UPLOADS, name)


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = "PromptBench/2"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_PUT(self): self.send_error(405)
    def do_DELETE(self): self.send_error(405)
    def do_PATCH(self): self.send_error(405)

    def authorised(self):
        return self.headers.get("Authorization", "") == EXPECTED

    def challenge(self):
        body = b"Unauthorised\n"
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Prompt Bench admin", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def json_out(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_app(self):
        # Keep optional DLC runtime mechanics separate from the monolithic HTML.
        path = os.path.join(ROOT, "prompt-bench.html")
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            return self.send_error(404)
        tag = b'<script src="/dynamic-sliders.js"></script>\n'
        marker = b"</body>"
        if marker in body and tag not in body:
            body = body.replace(marker, tag + marker, 1)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
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
            if query.get("all"):
                if not self.authorised():
                    return self.challenge()
            else:
                packs = [p for p in packs if not is_private(p)]
            return self.json_out(packs)

        if path in ("/admin", "/admin/", "/admin.html"):
            if not self.authorised():
                return self.challenge()
            self.path = "/admin.html"
            return super().do_GET()

        if path in ("/", "/prompt-bench.html"):
            return self.serve_app()
        elif path == "/prompt-bench-offline.html":
            # The offline build has the cast baked in. Never serve it publicly.
            if not self.authorised():
                return self.challenge()
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/api/upload", "/api/remove"):
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

        target = safe_upload_path(payload.get("name"))
        if not target:
            return self.json_out({"ok": False, "error": "a usable filename is required"}, 400)

        if path == "/api/remove":
            if not os.path.isfile(target):
                return self.json_out({"ok": False, "error": "no such uploaded pack"}, 404)
            try:
                os.remove(target)
            except OSError as exc:
                return self.json_out({"ok": False, "error": str(exc)}, 500)
            return self.json_out({"ok": True, "removed": os.path.basename(target)})

        pack = payload.get("pack")
        if not isinstance(pack, dict):
            return self.json_out({"ok": False, "error": "pack must be a JSON object"}, 400)
        known = ("pack", "private", "shared", "masters", "people",
                 "categories", "dials", "variation", "fields")
        if not any(k in pack for k in known):
            return self.json_out({"ok": False, "error": "that file contains none of the recognised pack keys"}, 400)

        try:
            os.makedirs(UPLOADS, exist_ok=True)
            tmp = target + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(pack, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp, target)
        except OSError as exc:
            return self.json_out({"ok": False, "error": "could not write: %s" % exc}, 500)
        return self.json_out({"ok": True, "saved": os.path.basename(target)})

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
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
