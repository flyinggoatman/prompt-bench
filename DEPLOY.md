# Deployment brief for the Hostinger VPS agent

Copy everything below the line into your conversation with the agent. Fill in the three bracketed values first.

---

I want you to deploy a small, self contained web application called Prompt Bench onto this VPS as its own Docker Compose project. It is a static HTML page plus a small Python server. The main page is public and needs no login. A separate admin page at `/admin` is protected by HTTP Basic Auth and is the only thing that can write anything. Please follow the constraints below exactly; they matter more than speed.

## Non negotiable constraints

1. Do not modify, restart, recreate or reconfigure any existing container, Compose project, network or volume. In particular do not touch the Hermes Agent, Hermes Workspace, Traefik, Ollama, Open WebUI, code-server, Obsidian or the Alexa bridge. This project must be additive and isolated.
2. Before making any change, record the current state: `docker ps -a`, `docker network ls`, `docker compose ls`, the current firewall rules, and the disk usage. Save this to a dated file in the deployment directory so the change can be compared and reversed.
3. Every step must be reversible with a single logged command. Write a `ROLLBACK.md` in the deployment directory containing the exact commands to remove this deployment completely, then verify the rollback commands are correct before you consider the job done.
4. No credentials are to be written into any file that could be committed to a repository. The only credential this app needs is a Basic Auth username and password, and it lives in a `.env` file that is listed in `.gitignore`. Generate the password yourself with `openssl rand -base64 32`, show it to me once in the chat, and do not store it anywhere else.
5. The container runs as a non root user, with a read only root filesystem, all capabilities dropped, and no access to the Docker socket. The Compose file already specifies this. Do not weaken it.
6. The main page is deliberately public, so the port may be open. However, the admin page uses Basic Auth, which sends the password reversibly over plain HTTP. If a hostname and an existing Traefik with HTTPS are available, use that. If they are not, tell me so before you expose the port, and I will decide whether to accept plain HTTP or restrict it at the firewall.
7. Uploads are capped at 512 KB, must parse as JSON, must contain a recognised pack key, and are written only into `uploads/` with a sanitised filename. Do not relax any of these. Do not add an endpoint that accepts scripts or archives.
8. If anything in these instructions conflicts with what you find on the machine, stop and ask me rather than improvising.

## What you are deploying

The deployment bundle is `prompt-bench.zip`. Its contents are:

```
prompt-bench.html          the public application, one file, no dependencies
prompt-bench-offline.html  same app with my cast baked in, for offline use
admin.html                 the protected management page
server.py                  the server, Python standard library only
README.md                  documentation of the JSON pack format
packs/                     curated content, mounted read only
uploads/                   where admin installed packs land, the only writable path
legacy/                    the previous version of the app, kept for safety
deploy/Dockerfile
deploy/docker-compose.yml
deploy/.env.example
deploy/.gitignore
```

## What is public and what is not

Public, no credentials:
- `GET /` the app
- `GET /api/packs` every pack that is not marked private
- `GET /healthz`

Requires Basic Auth:
- `GET /admin` the management page
- `GET /api/packs?all=1` including private packs
- `GET /prompt-bench-offline.html`
- `POST /api/upload` and `POST /api/remove`

One pack, `packs/people/00-people.json`, is marked `"private": true`. It describes real people and must never be served publicly. The server excludes any pack with that flag from the public endpoint. Do not remove that flag, and do not add a route that bypasses the check.

## Steps

1. Create the directory `/srv/prompt-bench` and unpack the bundle into it. Move the four files from `deploy/` up into `/srv/prompt-bench/` so that `Dockerfile`, `docker-compose.yml`, `.env.example` and `.gitignore` sit beside `server.py`. The Dockerfile expects `prompt-bench.html`, `server.py`, `README.md`, `packs/` and `legacy/` in the build context.
2. Copy `.env.example` to `.env`. Set `BENCH_USER` to `[MY_USERNAME]` and `BENCH_PASS` to a freshly generated random passphrase. Confirm `.env` is in `.gitignore`.
3. Create an `uploads` directory beside `packs` if the bundle did not include one, and make sure the container user can write to it. It is the only writable path.
4. Choose the exposure method:
   - **Option 1, direct port.** Leave the `ports` block as it is. It publishes host port 8790. Then add a Hostinger firewall rule that allows TCP 8790 only from `[MY_IP_ADDRESS]` and denies it from everywhere else. Confirm the rule is active before the container starts.
   - **Option 2, Traefik.** Only use this if a Traefik instance is already routing for this host and you can identify its external Docker network name without modifying Traefik. Comment out the `ports` block, uncomment the `networks` and `labels` blocks, set the hostname to `[MY_HOSTNAME]`, and set the network name to the existing Traefik network. Do not create a new Traefik or a new certificate resolver.
5. Build and start: `docker compose up -d --build` from `/srv/prompt-bench`.
6. Verify from inside the VPS, and report each result to me:
   - `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/` returns `200`
   - `curl -s http://127.0.0.1:8790/api/packs | grep -c '"private": *true'` returns `0`
   - `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/admin` returns `401`
   - `curl -s -o /dev/null -w '%{http_code}' -u USER:PASS http://127.0.0.1:8790/admin` returns `200`
   - `curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8790/api/packs?all=1'` returns `401`
   - `curl -s -o /dev/null -w '%{http_code}' -X POST -d '{}' http://127.0.0.1:8790/api/upload` returns `401`
   - `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8790/prompt-bench-offline.html` returns `401`
   If the second check returns anything other than `0`, stop immediately and tell me. That would mean private data is being served publicly.
7. Verify from outside the VPS that the admin page is unreachable from any address other than mine, or that the Traefik route answers only over HTTPS.
8. Write `ROLLBACK.md` with these exact commands and confirm each one is correct for what you actually deployed:
   ```
   cd /srv/prompt-bench && docker compose down --rmi local --volumes
   # then remove the firewall rule you added, by its id
   # then: rm -rf /srv/prompt-bench   (only after I confirm)
   ```
9. Write a short `CHANGELOG.md` entry: date, what was created, which exposure option was used, the firewall rule id if any, and the rollback pointer.
10. Report back with: the public URL, the admin URL, the username, the password shown once, the exposure option used, the container status from `docker ps`, and the contents of `ROLLBACK.md`.

## How I will update it later

The image now carries both benches, both admin pages, `tools/` and `docs/`, and
Node. Node is there because the agent routes at `/api/agent/...` run the same
prompt engine the page uses rather than a second copy of it written in Python.
Without it those routes answer 501 and everything else works as before.

Adding content does not need a rebuild, and does not need you. I install packs myself from the admin page, which writes them into `uploads/`. JSON files dropped into `/srv/prompt-bench/packs/` by hand also appear on the next page load. Both folders are listed by the server on every request. Replacing `prompt-bench.html` or `server.py` needs `docker compose up -d --build`. Please note both of these in the changelog so I do not have to ask again.

## What this service does not do

It has no shell, no database, no outbound network calls and no script execution. The only write path is authenticated JSON pack upload into one folder. Everything a user types stays in their own browser, photos never reach the server, and my cast is pulled into my own browser's local storage rather than served to anyone. It is deliberately boring.
