# Prompt Bench packs

This folder contains the live reference implementations for Prompt Bench pack formats.

For the complete authoring contract, including every supported top-level DLC type, merge rules, routing rules, ZIP layouts and minimal JSON examples, read [`../DLC-FORMAT-GUIDE.md`](../DLC-FORMAT-GUIDE.md).

Current structure:

```text
packs/
  masters/      shared prompt blocks and master prompts
  people/       cast / character packs
  categories/   core stackable module categories
  controls/     wording, settings, castFields, discipline, dials, variation, fields
  dlc/          expansion wave one
  dlc2/         expansion wave two
```

The folder is organisational. Prompt Bench behaviour is determined by the JSON keys documented in the guide.

Finished distributable DLC should be published in `flyinggoatman/prompt-bench-packs`; this private repository remains the implementation and format reference.
