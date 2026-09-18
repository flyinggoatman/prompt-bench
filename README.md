# Prompt Bench

Prompt Bench assembles image prompts from a master prompt plus stackable modules and JSON packs. It can run locally in a browser or from the included server setup.

## Install or update from GitHub

Run this command from the directory where you want Prompt Bench installed:

```bash
curl -fsSL https://raw.githubusercontent.com/flyinggoatman/prompt-bench/main/install-public.sh | bash
```

This needs only `curl`, `tar` and internet access. It downloads the current public repository into the current directory. Existing local files that are not part of the repository are left in place.

## Run Prompt Bench

Open `prompt-bench.html` directly in a browser, or use the included server/Docker setup for automatic pack loading and the protected admin page.

## Documentation

The detailed Prompt Bench guide, pack format reference, sharing behaviour, server notes and patch-updater documentation are preserved in [docs/README.md](docs/README.md).

For the complete DLC schema and every supported pack mechanic, see [DLC-FORMAT-GUIDE.md](DLC-FORMAT-GUIDE.md).
