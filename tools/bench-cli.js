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

   For agents (tools/bench-agent.js):

     node tools/bench-cli.js manifest [--bench main|persona]   # what this is and how to drive it
     node tools/bench-cli.js compose --brief "the client's words" [--recipe r.json] [--json]
     node tools/bench-cli.js compose --input input.json --json # { brief, cast, recipe, fill }
     node tools/bench-cli.js suggest --brief "the client's words"
     node tools/bench-cli.js gaps --recipe recipe.json          # what is still open, as questions

   --public leaves out every pack marked private, exactly as the shareable
   prompt and the public server do. --allow-groups cast,other lets back in the
   private packs that name one of those unlock groups.

   A recipe may be a file, or - to read it from standard input. Packs are read
   from the packs directory beside this script, and from uploads if it exists.
   ------------------------------------------------------------------ */
"use strict";

const fs = require("fs");
const path = require("path");
const { createBench } = require("./bench-engine.js");
const { createAgent } = require("./bench-agent.js");

const REPO = path.resolve(__dirname, "..");

const PROFILES = {
  main: { bench: "main", name: "Prompt Bench", keyPrefix: "promptbench", borrow: null },
  persona: { bench: "persona", name: "Persona Bench", keyPrefix: "personabench",
             borrow: ["MEDIUM", "FINISH", "PALETTE", "LIGHT", "SHAPE", "FORMAT", "STRUCTURE"] }
};

function readPacks(publicOnly, groups) {
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
        if (publicOnly && data && (data.private || data.locked) && !unlocked(data, groups)) continue;
        if (data && data.nsfw) continue;   /* agents never see NSFW content */
        out.push({ name, path: path.relative(REPO, full).split(path.sep).join("/"), data: withoutNsfw(data) });
      }
    })(base);
  }
  return out.sort((a, b) => a.path.localeCompare(b.path));
}

/* Anything marked "nsfw": true is left out before the engine sees it, whoever
   is asking: a master, a person, a category (with its modules) or a module. */
function withoutNsfw(data) {
  if (!data || typeof data !== "object" || !JSON.stringify(data).match(/"nsfw"\s*:\s*true/)) return data;
  const out = Object.assign({}, data);
  const keep = x => !(x && x.nsfw);
  for (const key of ["masters", "people", "shared", "dials", "variation", "fields", "discipline", "castFields"]) {
    if (Array.isArray(data[key])) out[key] = data[key].filter(keep);
  }
  if (Array.isArray(data.categories)) {
    out.categories = data.categories.filter(keep).map(c => Object.assign({}, c, { items: (c.items || []).filter(keep) }));
  }
  return out;
}

/* A private pack that names an unlock group is readable by a caller holding
   that group (--allow-groups), as the server grants after a right code. */
function unlocked(data, groups) {
  if (!groups || !groups.length) return false;
  if (groups.indexOf("*") > -1) return true;
  const mine = Array.isArray(data.unlock) ? data.unlock : (data.unlock ? [data.unlock] : []);
  return mine.some(g => groups.indexOf(String(g)) > -1);
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
  let input = null;
  try { input = readRecipe(opts.input); }
  catch (e) { die("could not read the input: " + e.message, 2); }
  if (input && typeof input !== "object") die("the input must be a JSON object", 2);
  const agentCommand = ["manifest", "compose", "suggest", "gaps", "questions"].indexOf(command) > -1;
  if (input && input.bench && !opts.bench) opts.bench = input.bench;

  const wanted = opts.bench || benchName || (recipe && recipe.bench) || "main";
  const profile = PROFILES[wanted];
  if (!profile) die("unknown bench: " + wanted + ". Use main or persona.", 2);

  const groups = typeof opts["allow-groups"] === "string" ? opts["allow-groups"].split(",").map(x => x.trim()).filter(Boolean) : [];
  const bench = createBench({ packs: readPacks(!!opts.public, groups), profile });
  const agent = createAgent(bench, { baseUrl: opts.base || "" });
  const say = (value) => process.stdout.write(JSON.stringify(value, null, 2) + "\n");

  if (agentCommand) {
    const brief = opts.brief === true ? "" : (opts.brief || (input && input.brief) || "");
    switch (command) {
      case "manifest":
        return say(agent.manifest({ scope: opts.public ? "public" : "all" }));
      case "suggest": {
        const base = recipe || (input && input.recipe && typeof input.recipe === "object" ? input.recipe : null);
        if (base) bench.fromRecipe(base);
        const usable = bench.offered().usable.map(r => r.n);
        return say(agent.suggest(brief, { usable }));
      }
      case "gaps":
      case "questions": {
        if (recipe) bench.fromRecipe(recipe);
        const g = agent.gaps();
        if (command === "questions") return process.stdout.write(agent.questions(g) + "\n");
        return say({ gaps: g, questions: agent.questions(g) });
      }
      case "compose": {
        const payload = Object.assign({}, input || {});
        if (brief) payload.brief = brief;
        if (recipe) payload.recipe = Object.assign({}, payload.recipe || {}, recipe);
        const result = agent.compose(payload);
        if (opts.json) return say(result);
        const mode = opts.mode || "prompt";
        process.stdout.write((result[mode] || result.prompt) + "\n");
        if (result.questions) process.stderr.write("\nStill open:\n" + result.questions + "\n");
        return;
      }
    }
  }

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
