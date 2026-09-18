# GitHub pack repository import

Prompt Bench Admin can import pack JSON files directly from a GitHub repository.

## Use

1. Open `/admin`.
2. Find **Import GitHub packs**.
3. Paste a repository URL such as `https://github.com/owner/repository`.
4. For a public repository, leave the token box empty.
5. For a private repository, either configure `GITHUB_TOKEN` on the Prompt Bench server or paste a suitable GitHub token into the one-use token box.
6. Press **Import GitHub packs**.

The importer scans JSON files in the repository and installs only files containing recognised Prompt Bench payload keys. Catalogue files and unrelated JSON are skipped.

Recognised payload keys are `shared`, `masters`, `people`, `categories`, `wording`, `settings`, `castFields`, `discipline`, `dials`, `variation`, and `fields`.

Imported files are written to `uploads/` using deterministic filenames prefixed with the GitHub owner and repository. Importing the same repository again updates files with the same source paths.

## Safety limits

- Only HTTPS links on `github.com` are accepted.
- The GitHub archive is capped at 8 MB.
- Individual JSON files are capped at 512 KB.
- At most 250 JSON files are examined.
- At most 150 valid Prompt Bench pack files are installed from one repository.
- JSON is parsed as data only. Pack content is never executed.
- The optional token entered in Admin is sent only to the authenticated Prompt Bench server for that import request. The page clears the field after the request and Prompt Bench does not write it to pack files or logs.

For long-term private-repository access, prefer setting `GITHUB_TOKEN` in the server environment instead of repeatedly pasting a token into the page.
