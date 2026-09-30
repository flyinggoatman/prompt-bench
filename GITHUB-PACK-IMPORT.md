# GitHub pack repository import

Prompt Bench Admin can import pack JSON files directly from a GitHub repository.

## Use

1. Open `/admin`.
2. Find **Import GitHub packs**.
3. Paste a repository, branch or folder link. All of these work: `https://github.com/owner/repository`, `github.com/owner/repository`, `…/repository.git`, `…/tree/<branch>` (that branch instead of the default), `…/tree/<branch>/<folder>` (only packs in that folder).
4. For a public repository, leave the token box empty.
5. For a private repository, either configure `GITHUB_TOKEN` on the Prompt Bench server or paste a suitable GitHub token into the one-use token box.
6. Press **Import GitHub packs**.

The importer scans JSON files in the repository, and JSON files inside any `.zip` in the repository, and installs only files containing recognised Prompt Bench payload keys. Catalogue files and unrelated JSON are skipped. When nothing is installed, the error names a skipped file and the reason.

Recognised payload keys are `shared`, `masters`, `people`, `categories`, `wording`, `settings`, `castFields`, `discipline`, `dials`, `variation`, and `fields`.

Imported files are written to `uploads/` using deterministic filenames prefixed with the GitHub owner and repository. Importing the same repository again updates files with the same source paths.

## Safety limits

- Only `github.com` links are accepted.
- The GitHub archive is capped at 25 MB (`BENCH_GITHUB_MAX_MB`).
- A `.zip` inside the repository is read only one level deep, up to 8 MB and 500 entries.
- Individual JSON files are capped at 512 KB.
- At most 250 JSON files are examined.
- At most 150 valid Prompt Bench pack files are installed from one repository.
- JSON is parsed as data only. Pack content is never executed.
- The optional token entered in Admin is sent only to the authenticated Prompt Bench server for that import request. The page clears the field after the request and Prompt Bench does not write it to pack files or logs.

For long-term private-repository access, prefer setting `GITHUB_TOKEN` in the server environment instead of repeatedly pasting a token into the page.

## When an import fails

The admin page shows why:

- **no such repository or branch**: the link is wrong, or the repository is private and no token is set.
- **rate limit used up**: GitHub allows 60 anonymous requests an hour per server, shared by everything on it. Set `GITHUB_TOKEN` (the compose file passes it into the container) or wait for the reset time given.
- **token rejected**: `GITHUB_TOKEN` or the one-use token is wrong or expired.
- **no valid Prompt Bench pack JSON files**: the message names a skipped file and why (not a pack, invalid JSON, too large).

The server log (`docker logs`) records each refusal too.

## Zip files on the admin page

The **Install local packs** card also takes `.zip` files. The zip is opened in the browser and each JSON pack inside is uploaded on its own, so the server never receives an archive.
