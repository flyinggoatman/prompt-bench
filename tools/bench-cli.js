#!/usr/bin/env node
/* ------------------------------------------------------------------
   Prompt Bench from a command line, for agents and scripts.

   The same engine the page uses, so anything this prints is what a person
   would have got by clicking. Everything speaks JSON except the assembled
   prompt itself, which is the text you paste into an image model.

     node tools/bench-cli.js capabilities [--bench main|persona]
     node tools/bench-cli.js model [--bench main|persona] [--category KEY]
     node tools/bench-cli.js offered --recipe recipe.json
     node tools/bench-cli.js assemble --recipe recipe.json [--mode prompt|followup|shareable]
     node tools/bench-cli.js recipe --recipe recipe.json      # normalise and check one

   A recipe may be a file, or - to read it from standard input. Packs are read
   from the packs directory beside this script, and from uploads if it exists.
   ------------------------------------------------------------------ */
"use strict";

const fs = require("fs");
const path = require("path");
const { createBench } = require("./bench-engine.js");

const REPO = path.resolve(__dirname, "..");

const PROFILES = {
  main: { bench: "main", name: "Prompt Bench", keyPrefix: "promptbench", borrow: null },
  persona: { bench: "persona", name: "Persona Bench", keyPrefix: "personabench",
             borrow: ["MEDIUM", "FINISH", "PALETTE", "LIGHT", "SHAPE", "FORMAT", "STRUCTURE"] }
};

function readPacks() {
  const out = [];
  for (const dir of ["packs", "uploads"]) {
    const base = path.join(REPO, dir);
    if (!fs.existsSync(base)) continue;
    (function walk(d) {
      for (const name of fs.readdirSync(d).sort()) {
        const full = path.join(d, name);
        if (fs.statSync(full).isDirectory()) { walk(full); continue; }
        if (!name.toLowerCase().endsWith(".json")) continue;
        let data;
        try { data = JSON.parse(fs.readFileSync(full, "utf8")); }
        catch (e) { continue; }   /* a broken pack is skipped, as in the page */
        out.push({ name, path: path.relative(REPO, full).split(path.sep).join("/"), data });
      }
    })(base);
  }
  return out.sort((a, b) => a.path.localeCompare(b.path));
}

function args(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) out[a.slice(2)] = (argv[i + 1] && !argv[i + 1].startsWith("--")) ? argv[++i] : true;
    else out._.push(a);
  }
  return out;
}

function readRecipe(where) {
  if (!where) return null;
  const raw = where === "-" ? fs.readFileSync(0, "utf8") : fs.readFileSync(where, "utf8");
  return JSON.parse(raw);
}

function die(message, code) {
  process.stderr.write(message + "\n");
  process.exit(code === undefined ? 1 : code);
}

function main() {
  const opts = args(process.argv.slice(2));
  const command = opts._[0];
  const benchName = opts.bench || (opts.recipe ? null : "main");

  if (!command || command === "help" || opts.help) {
    process.stdout.write(fs.readFileSync(__filename, "utf8").split("*/")[0].split("---\n")[1] + "\n");
    return;
  }

  let recipe = null;
  try { recipe = readRecipe(opts.recipe); }
  catch (e) { die("could not read the recipe: " + e.message, 2); }

  const wanted = benchName || (recipe && recipe.bench) || "main";
  const profile = PROFILES[wanted];
  if (!profile) die("unknown bench: " + wanted + ". Use main or persona.", 2);

  const bench = createBench({ packs: readPacks(), profile });

  if (recipe) {
    if (recipe.bench && recipe.bench !== profile.bench) {
      die(`this recipe is for the ${recipe.bench} bench, and you asked for ${profile.bench}`, 2);
    }
    const applied = bench.fromRecipe(recipe);
    if (applied.missing > 0 && !opts.force) {
      const why = [];
      if (applied.notInstalled.length) {
        why.push(`${applied.notInstalled.length} are not installed: install the packs they came from`);
      }
      if (applied.wrongMaster.length) {
        why.push(`${applied.wrongMaster.length} belong to another master, and this recipe chose `
          + `${applied.master}: pick the master they were written for`);
      }
      if (applied.tooFewCharacters.length) {
        why.push(`${applied.tooFewCharacters.length} need more characters than the cast has, and have `
          + `no wording for this size: raise castCount`);
      }
      const detail = (applied.notInstalled.concat(applied.wrongMaster, applied.tooFewCharacters))
        .slice(0, 5).map(t => "    " + t).join("\n");
      die(`${applied.missing} of ${applied.asked} modules did not apply.\n  `
        + why.join("\n  ") + "\n" + detail
        + "\n  Pass --force to build without them.", 3);
    }
  }

  const say = (value) => process.stdout.write(JSON.stringify(value, null, 2) + "\n");

  switch (command) {
    case "capabilities":
      return say(bench.capabilities());
    case "model": {
      const model = bench.model();
      if (opts.category) {
        const found = model.categories.find(c => c.key === opts.category);
        if (!found) die("no such category: " + opts.category, 2);
        return say(found);
      }
      return say(model);
    }
    case "offered":
      return say(bench.offered());
    case "recipe":
      return say(bench.toRecipe(recipe && recipe.name));
    case "assemble": {
      const mode = opts.mode || "prompt";
      if (["prompt", "followup", "shareable"].indexOf(mode) < 0) {
        die("unknown mode: " + mode + ". Use prompt, followup or shareable.", 2);
      }
      const text = bench.assemble(mode);
      if (opts.json) return say({ bench: profile.bench, mode, words: text.trim().split(/\s+/).length, text });
      return process.stdout.write(text + "\n");
    }
    default:
      die("unknown command: " + command + ". Try help.", 2);
  }
}

main();
