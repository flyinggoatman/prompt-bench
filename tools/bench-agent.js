/* ------------------------------------------------------------------
   Prompt Bench agent layer.

   Everything an AI agent needs on top of the engine, written once and used
   in three places: inlined into the Studio page (window.PromptBench), required
   by tools/bench-cli.js, and so reached through the server's /api/agent routes.

   It only ever talks to the engine through the engine's public API
   (capabilities, model, offered, getState, setState, fromRecipe, toRecipe,
   assemble), so the prompt text is always the engine's own.

     const { createAgent } = require("./bench-agent.js");
     const agent = createAgent(bench);          // bench = createBench(...)
     agent.compose({ brief: "A riso poster of three friends, no text" });

   Four things, each a plain function returning plain JSON:

     manifest()        what this is, how to drive it, what it accepts
     suggest(brief)    read a client's own words and propose a recipe
     gaps()            what is still open, as questions with a place to answer
     compose(input)    brief + partial recipe + cast in, finished prompts out

   Suggestions never override a choice that was made explicitly. Anything the
   brief does not settle is reported as a gap rather than invented.
   ------------------------------------------------------------------ */
(function(root, factory){
  var api = factory();
  if(typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BenchAgent = api;
})(typeof self !== "undefined" ? self : this, function(){
  "use strict";

  var SCHEMA = "prompt-bench.agent/1";

  var STOP = {};
  ("a an the and or of to in on at for with by from as is are was were be been it its this that these those me my mine i we us our " +
   "you your he she they them their his her him some any very really just like want wants wanted would could should please make made " +
   "making draw drawing drawn image images picture pictures pic create generate generated something thing things can will do does did " +
   "have has had get got bit lot kind sort style styled look looking looks feel also about into over but not no so if then than there " +
   "here what who where when how all every each more most much many other same own one two three four five six seven eight nine ten " +
   "being into onto out up down off again ever even still yet only quite rather maybe perhaps need needs using use used show shows showing " +
   "put let way ok okay thanks thank hi hello new say says saying said tell told showing show shows go goes going").split(" ").forEach(function(w){ STOP[w] = true; });

  /* A client writes American or casual; the packs are written in British English. */
  var SYN = {
    color:"colour", colors:"colours", colored:"coloured", colorful:"colourful", gray:"grey", center:"centre", centered:"centred",
    riso:"risograph", watercolor:"watercolour", watercolors:"watercolour", favorite:"favourite", theater:"theatre",
    photo:"photograph", photos:"photograph", pic:"picture", pfp:"avatar",
    cozy:"cosy", humor:"humour", humorous:"funny", comic:"comic", manga:"manga", pixel:"pixel", neon:"neon",
    b:"", w:"", bw:"monochrome", monochromatic:"monochrome", pastel:"pastel", pastels:"pastel", crayons:"crayon",
    linocut:"linocut", lino:"linocut", woodcut:"woodcut", screen:"screen", screenprinted:"screenprint", screenprint:"screenprint",
    ink:"ink", inked:"ink", sketchy:"sketch", sketched:"sketch", doodle:"doodle", doodles:"doodle"
  };

  var NEG_CLAUSE = /\b(no|without|not|never|avoid|don't|dont|do not|doesn't|nothing|none of)\b/i;
  var NEG_PHRASING = /\b(do not|don't|never|avoid|avoiding|must not|should not|cannot|can't|refrain|no extra|without any)\b/i;

  function norm(w){
    w = String(w).toLowerCase().replace(/^'+|'+$/g, "");
    if(SYN[w] !== undefined) w = SYN[w];
    return w;
  }
  function stem(w){
    if(w.length > 4 && /ies$/.test(w)) return w.slice(0, -3) + "y";
    if(w.length > 5 && /ing$/.test(w)) return w.slice(0, -3);
    if(w.length > 4 && /ed$/.test(w)) return w.slice(0, -2);
    if(w.length > 4 && /(ss|x|z|ch|sh)es$/.test(w)) return w.slice(0, -2);
    if(w.length > 3 && /s$/.test(w) && !/ss$/.test(w)) return w.slice(0, -1);
    return w;
  }
  function tokens(text){
    var out = [];
    String(text || "").replace(/\{[^}]*\}/g, " ").toLowerCase().replace(/[a-z0-9']+/g, function(raw){
      var w = norm(raw);
      if(!w || w.length < 3 || STOP[w] || /^\d+$/.test(w)) return raw;
      out.push(stem(w));
      return raw;
    });
    return out;
  }
  function uniq(a){ var s = {}, o = []; a.forEach(function(x){ if(!s[x]){ s[x] = 1; o.push(x); } }); return o; }

  var RARE = 3.4, VERY_RARE = 4.4;
  /* Lanes where one rare word is decisive: "risograph", "beach", "snow",
     "beard". Elsewhere (poses, gags, moods) one word is too thin a reason, so
     it takes two. */
  var SINGLE_WORD_OK = ["MEDIUM","FINISH","PALETTE","LIGHT","SHAPE","SCENE","CONDITIONS",
    "SPECIES","FACE","EYES","SKIN","HAIR","FACIALHAIR","BODY","CLOTHING","ACCESSORIES","ICONIC","PETS","MOUNTS","SETTING","WEATHER"];
  var DIAL_WORDS = ["calm","quiet","still","peaceful","serene","sleepy","gentle","tranquil","chaos","chaotic","busy","manic","frantic","wild","mayhem","hectic",
    "warm","cosy","golden","cold","cool","icy","light","lighting","clean","crisp","minimal","tidy","polished","grungy","grunge","worn","distressed","scruffy","text","words","lettering","writing","title","caption"];
  var CAST_WORDS = ["friend","friends","people","person","character","characters","figure","figures","us","group","family","colleague","colleagues","man","woman","kid","kids","guy","girl","boy"];

  var NUMBER = { one:1, two:2, three:3, four:4, five:5, six:6, seven:7, eight:8, nine:9, both:2, pair:2, couple:2, trio:3 };

  /* Which master a brief is asking for, by the words people use for it. Keyed
     on words found in a master's name, so a pack's own master benefits too. */
  var MASTER_HINTS = {
    poster: ["poster","cover","album","magazine","flyer","advert","ad","gig","cereal","box","notice","billboard","leaflet","banner","print"],
    moment: ["moment","candid","scene","snapshot","happening","caught","everyday","slice","reaction","unposed"],
    set: ["sheet","set","avatar","icon","cards","card","flat","lay","grid","sticker","stickers","emoji","group icon","collection"],
    sequence: ["sequence","panel","panels","strip","storyboard","before","after","steps","escalating","comic strip","frames"],
    portrait: ["portrait","headshot","face","bust","close"],
    avatar: ["avatar","profile picture","profile","badge","discord","pfp"],
    persona: ["turnaround","reference","views","sheet","model sheet"],
    figure: ["full","figure","body","standing","outfit","head to toe","full length"]
  };

  function createAgent(engine, options){
    options = options || {};
    var baseUrl = options.baseUrl || "";

    function caps(){ return engine.capabilities(); }
    function model(){ return engine.model(); }
    function st(){ return engine.getState(); }
    function settings(){ return model().settings || {}; }
    function maxCast(){ return settings().maxCast || 5; }
    function styleKeys(){ var k = settings().styleFirst; return Array.isArray(k) ? k : ["MEDIUM","FINISH","PALETTE","LIGHT"]; }

    /* ---------------- index ---------------- */
    var indexCache = null;
    function index(){
      var m = model(), key = m.count + ":" + m.categories.length + ":" + (m.categories[0] && m.categories[0].items[0] ? m.categories[0].items[0].t : "");
      if(indexCache && indexCache.key === key) return indexCache;
      var df = {}, docs = [];
      m.categories.forEach(function(c){
        c.items.forEach(function(it){
          var toks = uniq(tokens(it.t));
          toks.forEach(function(t){ df[t] = (df[t] || 0) + 1; });
          docs.push({ cat: c, it: it, toks: toks, seq: tokens(it.t) });
        });
      });
      var N = Math.max(1, docs.length);
      var idf = function(t){ return Math.log(1 + N / (1 + (df[t] || 0))); };
      indexCache = { key: key, docs: docs, idf: idf };
      return indexCache;
    }

    /* ---------------- reading a brief ---------------- */
    function clauses(brief){
      return String(brief || "").split(/[.;!?\n]+|,\s*(?=(?:and\s+)?(?:no|without|but|not)\b)/i).map(function(s){ return s.trim(); }).filter(Boolean);
    }
    function negatives(brief){
      var out = [];
      clauses(brief).forEach(function(c){
        var m = c.match(/\b(?:no|without|not? (?:any|a|an)|never|avoid|don'?t (?:want|include|add|show|draw)(?: any| a| an)?|do not (?:want|include|add|show|draw)(?: any| a| an)?|nothing)\s+([a-z][a-z' -]{1,40})/i);
        if(m){
          var thing = m[1].replace(/\b(please|at all|thanks?|in it|in the (?:image|picture)|anywhere)\b/gi, "").replace(/\s+/g, " ").trim();
          if(thing && !/^(text|words|lettering|writing)$/i.test(thing)) out.push(thing);
        }
      });
      return uniq(out).slice(0, 6);
    }
    function positiveText(brief){
      return clauses(brief).filter(function(c){ return !NEG_CLAUSE.test(c); }).join(". ").replace(/\s+/g, " ").trim();
    }
    function lettering(brief){
      var out = [];
      String(brief || "").replace(/["“”]([^"“”]{1,80})["“”]/g, function(w, s){ out.push(s.trim()); return w; });
      return out.filter(Boolean);
    }
    function castCountFrom(brief){
      var b = " " + String(brief || "").toLowerCase() + " ";
      var m;
      if(/\b(nobody|no one|no people|no characters|no figures|empty (?:room|street|scene)|landscape only)\b/.test(b)) return { value: 0, why: "the brief asks for nobody in the picture" };
      if((m = b.match(/\b(two|three|four|five|six|seven|eight|nine|[2-9]) of us\b/))) return { value: NUMBER[m[1]] || +m[1], why: '"' + m[0].trim() + '"' };
      if((m = b.match(/\bme and (?:my )?(two|three|four|five|[2-5]) \w+/))) return { value: (NUMBER[m[1]] || +m[1]) + 1, why: '"' + m[0].trim() + '"' };
      if((m = b.match(/\b(two|three|four|five|six|seven|eight|nine|[2-9]) (?:people|characters|friends|persons|figures|kids|children|colleagues|coworkers|carers|pets|cats|dogs|siblings|women|men)\b/))) return { value: NUMBER[m[1]] || +m[1], why: '"' + m[0].trim() + '"' };
      if((m = b.match(/\b(both of us|the two of us|a couple|me and (?:my )?\w+)\b/))) return { value: 2, why: '"' + m[0].trim() + '"' };
      if((m = b.match(/\b(just me|only me|solo|by myself|on my own|of me\b|portrait|headshot|avatar of me|a person|one person|a man|a woman|a character)\b/))) return { value: 1, why: '"' + m[0].trim() + '"' };
      if((m = b.match(/\b(trio)\b/))) return { value: 3, why: '"trio"' };
      if((m = b.match(/\b(?:my|our|a|the) (cat|dog|kitten|puppy|pet|rabbit|horse|parrot|hamster|lizard|snake)\b/))) return { value: 1, why: '"' + m[0].trim() + '", an animal', animal: true };
      return null;
    }
    function dialHints(brief){
      var b = String(brief || "").toLowerCase(), out = [], have = {};
      model().dials.forEach(function(d){ have[d.id] = d; });
      function put(id, value, why){ if(have[id]){ var d = have[id], lo = d.min === undefined ? 0 : d.min, hi = d.max === undefined ? 10 : d.max; out.push({ id: id, label: d.label, value: Math.max(lo, Math.min(hi, value)), why: why }); } }
      var q = lettering(brief);
      if(q.length){ var n = 0; q.forEach(function(s){ n += s.split(/\s+/).length; }); put("words", Math.max(n, 3), "the brief quotes exact words to letter"); }
      else if(/\b(no (?:text|words|lettering|writing)|without (?:text|words|lettering)|wordless|textless)\b/.test(b)) put("words", 0, "the brief asks for no text");
      else if(/\b(title|caption|headline|slogan|label|sign|says|saying|reads|lettering)\b/.test(b)) put("words", 8, "the brief mentions lettering");
      if(/\b(calm|quiet|still|peaceful|serene|sleepy|gentle|tranquil)\b/.test(b)) put("energy", 2, "calm words in the brief");
      else if(/\b(chaos|chaotic|busy|manic|frantic|wild|mayhem|hectic|explosive|action)\b/.test(b)) put("energy", 9, "busy words in the brief");
      if(/\b(warm|cosy|cozy|golden|sunset|summer|autumn|fireside)\b/.test(b)) put("warmth", 8, "warm words in the brief");
      else if(/\b(cold|cool|icy|winter|frosty|blue hour|night)\b/.test(b)) put("warmth", 2, "cool words in the brief");
      if(/\b(clean|crisp|minimal|tidy|polished)\b/.test(b)) put("divergence", 2, "clean words in the brief");
      else if(/\b(grungy|grunge|worn|distressed|scruffy|battered|damaged|zine|photocopied|xerox)\b/.test(b)) put("divergence", 9, "rough words in the brief");
      return out;
    }

    /* ---------------- suggest ---------------- */
    function scoreMasters(brief){
      var toks = uniq(tokens(brief)), low = " " + String(brief || "").toLowerCase() + " ";
      var ix = index();
      return model().masters.map(function(m){
        var name = String(m.name || "").toLowerCase(), score = 0, why = [];
        Object.keys(MASTER_HINTS).forEach(function(k){
          if(name.indexOf(k) < 0) return;
          MASTER_HINTS[k].forEach(function(h){ if(low.indexOf(" " + h + " ") > -1 || low.indexOf(" " + h + "s ") > -1){ score += 3; why.push(h); } });
        });
        if(low.indexOf(" " + name + " ") > -1){ score += 4; why.push(name); }
        var mt = uniq(tokens((m.name || "") + " " + (m.blurb || "")));
        toks.forEach(function(t){ if(mt.indexOf(t) > -1){ score += ix.idf(t) * 0.35; why.push(t); } });
        return { id: m.id, name: m.name, score: Math.round(score * 100) / 100, why: uniq(why) };
      }).sort(function(a, b){ return b.score - a.score; });
    }

    function suggest(brief, opt){
      opt = opt || {};
      var ix = index(), out = { brief: String(brief || "") };
      var masters = scoreMasters(brief);
      out.masters = masters;
      out.master = masters[0] && masters[0].score >= 3 ? masters[0] : null;
      out.castCount = castCountFrom(brief);
      if(out.castCount && out.castCount.value > maxCast()) out.castCount = { value: maxCast(), why: out.castCount.why + ", capped at " + maxCast() };
      out.dials = dialHints(brief);
      out.lettering = lettering(brief);
      out.negatives = negatives(brief);
      out.fieldText = positiveText(brief);
      /* Modules are matched on what the client asked for, never on what they
         asked to leave out, and not on the words already spent choosing the
         master, the cast size or a dial: "poster", "calm" and "friends" say
         nothing about which scene to draw. */
      var spent = {};
      (out.master ? out.master.why.filter(function(w){ return w.indexOf(" ") < 0; }) : []).concat(DIAL_WORDS, CAST_WORDS).forEach(function(w){ tokens(w).forEach(function(t){ spent[t] = true; }); });
      var q = tokens(String(out.fieldText).replace(/["“”][^"“”]*["“”]/g, " ")).filter(function(t){ return !spent[t]; }), qs = uniq(q);

      /* Modules are scored against what is usable for the master and cast
         size in hand, so a suggestion is never something the engine would
         hold back. */
      var usable = {};
      if(opt.usable) opt.usable.forEach(function(n){ usable[n] = true; });
      var bigrams = [];
      for(var i = 0; i + 1 < q.length; i++) bigrams.push(q[i] + " " + q[i+1]);
      var per = {};
      ix.docs.forEach(function(d){
        if(opt.usable && !usable[d.it.n]) return;
        var matched = [], score = 0;
        qs.forEach(function(t){ if(d.toks.indexOf(t) > -1){ matched.push(t); score += ix.idf(t); } });
        if(!matched.length) return;
        var seq = d.seq.join(" ");
        bigrams.forEach(function(bg){ if(seq.indexOf(bg) > -1) score += 2; });
        score = score / Math.sqrt(1 + d.toks.length / 12);
        /* Confident only: two distinctive words, or one rare one. A lane the
           brief does not really speak to stays empty and becomes a question. */
        var rare = matched.filter(function(t){ return ix.idf(t) >= RARE; }).length;
        var single = SINGLE_WORD_OK.indexOf(d.cat.key) > -1 && matched.length === 1 && ix.idf(matched[0]) >= VERY_RARE && score >= 3.4;
        var ok = (matched.length >= 2 && rare >= 1 && score >= (opt.threshold || 5)) || single;
        if(!ok) return;
        var key = d.cat.key;
        (per[key] = per[key] || []).push({ category: key, label: d.cat.label, n: d.it.n, text: d.it.t,
          score: Math.round(score * 100) / 100, matched: matched });
      });
      out.modules = [];
      out.alternatives = {};
      /* One word justifies one lane. "comic, ink, flat colour" is a medium;
         having spent those words there, they cannot also pick a format. The
         strongest match claims its words first. */
      var best = [];
      Object.keys(per).forEach(function(k){
        per[k].sort(function(a, b){ return b.score - a.score; });
        best.push(per[k]);
        if(per[k].length > 1) out.alternatives[k] = per[k].slice(1, 4);
      });
      var sk = styleKeys();
      best.sort(function(a, b){
        var sa = sk.indexOf(a[0].category) > -1 ? 1 : 0, sb = sk.indexOf(b[0].category) > -1 ? 1 : 0;
        return (sb - sa) || (b[0].score - a[0].score);
      });
      var claimed = {};
      best.forEach(function(list){
        for(var j = 0; j < list.length && j < 4; j++){
          var c = list[j], left = c.matched.filter(function(t){ return !claimed[t]; });
          var rareLeft = left.filter(function(t){ return ix.idf(t) >= RARE; }).length;
          var fine = (left.length >= 2 && rareLeft >= 1) ||
                     (left.length === 1 && SINGLE_WORD_OK.indexOf(c.category) > -1 && ix.idf(left[0]) >= VERY_RARE);
          if(!fine) continue;
          left.forEach(function(t){ claimed[t] = true; });
          out.modules.push(c);
          break;
        }
      });
      var order = {}; model().categories.forEach(function(c, i){ order[c.key] = i; });
      out.modules.sort(function(a, b){ return order[a.category] - order[b.category]; });
      return out;
    }

    /* ---------------- gaps ---------------- */
    function fieldById(id){ return model().fields.filter(function(f){ return f.id === id; })[0]; }
    function contextField(){ return model().fields.filter(function(f){ return f.section === "CONTEXT" || f.section === "WHO THIS IS"; })[0]; }
    function briefField(){
      var s = settings(), f = s.briefField && fieldById(s.briefField);
      if(f) return f;
      return fieldById("extras") || model().fields.filter(function(x){ return !x.attachTo && x.section !== "CONTEXT"; })[0] || null;
    }
    function avoidField(){ return model().fields.filter(function(f){ return f.attachTo; })[0] || null; }
    function optionsFor(key, limit){
      var off = engine.offered();
      return off.usable.filter(function(r){ return r.category === key; }).slice(0, limit || 12).map(function(r){ return { n: r.n, text: r.text }; });
    }

    function gaps(){
      var s = st(), m = model(), off = engine.offered(), out = [];
      var n = Math.max(0, Math.min(maxCast(), parseInt(s.castCount, 10) || 0));
      var requirePhoto = settings().requirePhoto !== false;
      function add(g){ out.push(g); }
      if(!m.masters.length) add({ id: "master", level: "blocker", question: "No master prompt is installed.", fill: { path: "packs" } });
      var chosenIn = {};
      m.categories.forEach(function(c){ c.items.forEach(function(it){ if(s.on[it.n]) (chosenIn[c.key] = chosenIn[c.key] || []).push(it); }); });
      var usableIn = {};
      off.usable.forEach(function(r){ usableIn[r.n] = r; });
      var live = {};
      Object.keys(chosenIn).forEach(function(k){ live[k] = chosenIn[k].filter(function(it){ return usableIn[it.n]; }); });

      if(n === 0 && !s.castOpen) add({ id: "castCount", level: "should", about: "cast",
        question: "How many people or animals are in the image? With none set, the image model decides who appears.",
        fill: { path: "castCount", example: 2 } });
      for(var i = 0; i < n; i++){
        var p = s.cast[i] || {}, nm = String(p.name || "").trim(), who = nm || ("character " + (i + 1));
        if(!nm && !String(p.desc || "").trim()){
          add({ id: "cast." + i + ".name", level: "blocker", about: "cast", slot: i,
            question: "Who is character " + (i + 1) + "? A name (or a label) and a short description.",
            fill: { path: "cast[" + i + "].name", example: "Mara" } });
          continue;
        }
        m.castFields.forEach(function(f){
          if(p.kind === "animal" && f.outfitRule) return;
          if(String(p[f.key] || "").trim() || String(p.desc || "").trim()) return;
          var level = f.key === "marker" ? "should" : (f.key === "looks" ? "should" : "could");
          add({ id: "cast." + i + "." + f.key, level: level, about: "cast", slot: i,
            question: (f.label || f.key) + " for " + who + ": " + (f.hint || ""),
            fill: { path: "cast[" + i + "]." + f.key } });
        });
        if(requirePhoto && nm && !p.photo) add({ id: "cast." + i + ".photo", level: "note", about: "photo", slot: i,
          question: "No reference photo is marked for " + who + ". The prompt will ask the image model for one before drawing. If a photo will be attached, set cast[" + i + "].photo to true.",
          fill: { path: "cast[" + i + "].photo", example: true } });
      }
      var med = m.categories.filter(function(c){ return c.key === "MEDIUM"; })[0];
      if(med && !(live.MEDIUM || []).length) add({ id: "module.MEDIUM", level: "should", about: "style",
        question: "What physical medium is it made in? Without one, most models fall back on a glossy digital look.",
        fill: { path: "modules", category: "MEDIUM" }, options: optionsFor("MEDIUM", 14) });
      var pal = m.categories.filter(function(c){ return c.key === "PALETTE"; })[0];
      if(pal && !(live.PALETTE || []).length) add({ id: "module.PALETTE", level: "could", about: "style",
        question: "Which colours? A named palette stops the model choosing its default one.",
        fill: { path: "modules", category: "PALETTE" }, options: optionsFor("PALETTE", 10) });
      var ctx = contextField();
      if(ctx && n > 1 && !String(s.fields[ctx.id] || "").trim()) add({ id: "field." + ctx.id, level: "should", about: "brief",
        question: (ctx.label || ctx.id) + ": " + (ctx.hint || ""), fill: { path: "fields." + ctx.id } });
      ["FORMAT","MEDIUM","FRAMING","SHAPE","CROP","STRUCTURE"].forEach(function(k){
        if((live[k] || []).length > 1) add({ id: "conflict." + k, level: "blocker", about: "conflict",
          question: (live[k].length) + " " + k.toLowerCase() + " modules compete. Keep one.",
          fill: { path: "modules", category: k }, options: live[k].map(function(it){ return { n: it.n, text: it.t }; }) });
      });
      var words = m.dials.filter(function(d){ return d.id === "words"; })[0], text = live.TEXT || [];
      if(words && text.length){
        var wv = s.dials.words;
        var wants = text.filter(function(it){ return !/^No text anywhere/i.test(it.t); });
        var bans = text.filter(function(it){ return /^No text anywhere/i.test(it.t); });
        if(wv === 0 && wants.length) add({ id: "conflict.words", level: "blocker", about: "conflict", question: "A Text module asks for lettering but the words dial is at 0.", fill: { path: "dials.words", example: 6 } });
        if(wv > 0 && bans.length) add({ id: "conflict.words", level: "blocker", about: "conflict", question: "The 'No text' module contradicts the words dial at " + wv + ".", fill: { path: "dials.words", example: 0 } });
      }
      m.fields.forEach(function(f){
        if(f.attachTo) return;
        var v = String(s.fields[f.id] || ""), hit = v.match(NEG_PHRASING);
        if(hit) add({ id: "phrasing." + f.id, level: "should", about: "phrasing",
          question: (f.label || f.id) + " says \"" + hit[0] + "\". Naming a thing tends to summon it; describe what fills that space instead, and put true bans in the keep-out field.",
          fill: { path: "fields." + f.id } });
      });
      var held = 0; Object.keys(chosenIn).forEach(function(k){ chosenIn[k].forEach(function(it){ if(!usableIn[it.n]) held++; }); });
      if(held) add({ id: "held", level: "note", about: "modules", question: held + " chosen module" + (held === 1 ? " is" : "s are") + " held back by the master or cast size, and are not in the prompt.", fill: { path: "castCount" } });
      var rank = { blocker: 0, should: 1, could: 2, note: 3 };
      out.sort(function(a, b){ return rank[a.level] - rank[b.level]; });
      return out;
    }

    function questionsText(list){
      list = list || gaps();
      var main = list.filter(function(g){ return g.level === "blocker" || g.level === "should"; });
      var extra = list.filter(function(g){ return g.level === "could"; });
      if(!main.length && !extra.length) return "";
      var line = function(g, i){
        var o = g.options && g.options.length ? "\n   Options: " + g.options.slice(0, 6).map(function(x){ return x.text.split(/\.\s/)[0]; }).join(" / ") : "";
        return (i + 1) + ". " + g.question + o;
      };
      var out = main.map(line).join("\n");
      if(extra.length) out += (out ? "\n\nIf you have a moment:\n" : "") + extra.map(line).join("\n");
      return out;
    }

    /* ---------------- sharing ---------------- */
    function leakScan(text){
      var s = st(), hits = [];
      (s.cast || []).forEach(function(p){
        var nm = String(p.name || "").trim();
        if(nm.length >= 3 && new RegExp("\\b" + nm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "i").test(text)) hits.push(nm);
        model().castFields.concat([{ key: "desc" }]).forEach(function(f){
          var v = String(p[f.key] || "").trim().replace(/[.\s]+$/, "");
          if(v.length >= 16 && text.indexOf(v) > -1) hits.push("a cast description");
        });
      });
      model().fields.forEach(function(f){
        var v = String(s.fields[f.id] || "").trim();
        if(v.length >= 24 && text.indexOf(v) > -1) hits.push((f.label || f.id) + " text");
      });
      return uniq(hits);
    }

    /* ---------------- compose ---------------- */
    function modulesToTexts(list){
      var m = model(), byN = {}, texts = [], unknown = [];
      m.categories.forEach(function(c){ c.items.forEach(function(it){ byN[it.n] = it; }); });
      (list || []).forEach(function(x){
        if(typeof x === "number" || /^\d+$/.test(String(x))){ var it = byN[+x]; if(it) texts.push(it.t); else unknown.push(x); }
        else if(x && typeof x === "object" && x.text) texts.push(x.text);
        else if(typeof x === "string") texts.push(x);
      });
      return { texts: texts, unknown: unknown };
    }
    function catOfText(t){
      var k = null; model().categories.forEach(function(c){ c.items.forEach(function(it){ if(it.t === t) k = c.key; }); });
      return k;
    }
    function normaliseCast(cast){
      var fields = model().castFields;
      return (cast || []).slice(0, maxCast()).map(function(p){
        if(typeof p === "string") p = { name: p };
        var out = { name: String(p.name || p.label || "").trim(), kind: p.kind === "animal" ? "animal" : "person", desc: String(p.desc || p.description || "") };
        fields.forEach(function(f){ if(p[f.key] !== undefined) out[f.key] = String(p[f.key]); });
        /* The engine only needs to know that a photo exists; an agent cannot
           hand over the image itself, so true stands in for it. */
        if(p.photo) out.photo = (typeof p.photo === "string" && p.photo.indexOf("data:") === 0) ? p.photo : "attached";
        return out;
      });
    }

    function compose(input){
      input = input || {};
      var recipe = JSON.parse(JSON.stringify(input.recipe || {}));
      /* A base recipe (the page's current setup) counts as explicit: the brief
         only fills what neither the base nor the input settles. */
      if(input.base) Object.keys(input.base).forEach(function(k){ if(recipe[k] === undefined && k !== "cast") recipe[k] = JSON.parse(JSON.stringify(input.base[k])); });
      var brief = String(input.brief || "");
      var fill = input.fill === undefined ? "empty" : input.fill;   /* "empty" | "none" */
      var decisions = [];
      var cur = st();

      var cast = input.cast ? normaliseCast(input.cast) : (recipe.cast ? normaliseCast(recipe.cast) : null);

      /* A fresh compose starts from nothing: no text boxes, dials at their
         pack defaults, no switches left over from whoever used this engine
         last. Only a compose that is told to keep the current setup (the
         Studio's own "read this brief" button) carries anything over. */
      if(!input.keepCast && !input.base){
        var dd = {};
        model().dials.forEach(function(d){ dd[d.id] = d.value === undefined ? (d.min === undefined ? 0 : d.min) : d.value; });
        engine.setState({ fields: {}, dials: dd, on: {}, discipline: false, strangers: false, castOpen: false, followup: false });
        cur = st();
      }
      var sug = brief ? suggest(brief, {}) : null;

      /* How many characters. Explicit, then the cast given, then the brief. */
      var castCount = recipe.castCount;
      if(castCount === undefined && cast) castCount = cast.length;
      if(castCount === undefined && sug && sug.castCount){ castCount = sug.castCount.value; decisions.push({ what: "castCount", value: castCount, source: "brief", why: sug.castCount.why }); }
      if(castCount === undefined) castCount = input.keepCast ? cur.castCount : 0;

      /* Which master. */
      var master = recipe.master;
      if(!master && sug && sug.master){ master = sug.master.id; decisions.push({ what: "master", value: sug.master.name, source: "brief", why: sug.master.why.join(", ") }); }
      if(!master) master = input.keepCast ? cur.master : null;
      if(!master && model().masters.length) master = model().masters[0].id;

      engine.setState({ master: master, castCount: castCount, strangers: !!recipe.strangers });
      if(cast){
        /* A cast given here is the whole cast: the slots are rebuilt from it. */
        recipe.cast = cast;
      } else delete recipe.cast;

      /* Modules: explicit ones first, then one suggestion for each lane the
         recipe left empty, drawn only from what fits this master and cast. */
      var mt = modulesToTexts(recipe.modules);
      var chosen = mt.texts.slice(), filledCats = {};
      chosen.forEach(function(t){ var k = catOfText(t); if(k) filledCats[k] = true; });
      if(brief && fill !== "none"){
        var usable = engine.offered().usable.map(function(r){ return r.n; });
        var s2 = suggest(brief, { usable: usable });
        s2.modules.forEach(function(x){
          if(filledCats[x.category]) return;
          if((input.exclude || []).indexOf(x.category) > -1) return;
          chosen.push(x.text); filledCats[x.category] = true;
          decisions.push({ what: "module", category: x.category, value: x.text, n: x.n, source: "brief", why: "matched " + x.matched.join(", ") });
        });
        sug = s2;
      }
      recipe.modules = chosen;

      /* Dials: explicit values win. */
      recipe.dials = recipe.dials || {};
      if(sug) sug.dials.forEach(function(d){
        if(recipe.dials[d.id] === undefined){ recipe.dials[d.id] = d.value; decisions.push({ what: "dial", id: d.id, value: d.value, source: "brief", why: d.why }); }
      });

      /* Text boxes: the client's words go in as they wrote them, minus the
         clauses that ask for something to be left out. Those move to the one
         keep-out field, which is where a ban belongs. */
      recipe.fields = recipe.fields || {};
      if(brief && input.briefInto !== null){
        var bf = input.briefInto ? fieldById(input.briefInto) : briefField();
        var extra = [];
        if(sug && sug.fieldText) extra.push(sug.fieldText.replace(/[.\s]+$/, "") + ".");
        if(sug) sug.lettering.forEach(function(q){ extra.push('The exact words "' + q + '" appear once, hand lettered in the same medium, spelled exactly as written.'); });
        if(bf && recipe.fields[bf.id] === undefined && extra.length){ recipe.fields[bf.id] = extra.join(" "); decisions.push({ what: "field", id: bf.id, source: "brief", why: "the client's own words, without the clauses that ask for something to be left out" }); }
        var av = avoidField();
        if(av && sug && sug.negatives.length && recipe.fields[av.id] === undefined){
          recipe.fields[av.id] = sug.negatives.slice(0, av.limit || 3).join(", ");
          decisions.push({ what: "field", id: av.id, source: "brief", why: "the brief asked for these to be left out" });
        }
      }
      if(input.context && contextField() && recipe.fields[contextField().id] === undefined) recipe.fields[contextField().id] = String(input.context);

      recipe.castCount = castCount;
      recipe.master = master;
      if(recipe.discipline === undefined) recipe.discipline = input.discipline === undefined ? true : !!input.discipline;
      if(recipe.askQuestions === undefined && input.askQuestions !== undefined) recipe.askQuestions = !!input.askQuestions;
      if(recipe.seed === undefined && input.seed !== undefined) recipe.seed = input.seed;
      var applied = engine.fromRecipe(recipe);
      if(!cast && !input.keepCast) {
        /* No cast supplied and not keeping one: slots beyond what the brief
           names stay blank, so they become questions rather than borrowed
           people from a pack. */
        var s3 = engine.getState(), blank = [];
        for(var i = 0; i < s3.cast.length; i++){ var b = { name: "", kind: "person", photo: "", desc: "" }; model().castFields.forEach(function(f){ b[f.key] = ""; }); blank.push(b); }
        engine.setState({ cast: blank });
      }
      var out = {
        schema: SCHEMA, ok: true, bench: caps().bench,
        prompt: engine.assemble("prompt"),
        followup: engine.assemble("followup"),
        shareable: engine.assemble("shareable"),
        recipe: withoutPhotos(engine.toRecipe(recipe.name || "")),
        decisions: decisions,
        applied: applied,
        unknownModules: mt.unknown,
        gaps: gaps()
      };
      out.questions = questionsText(out.gaps);
      out.shareableLeaks = leakScan(out.shareable);
      out.words = (out.prompt.match(/\S+/g) || []).length;
      out.ready = !out.gaps.some(function(g){ return g.level === "blocker"; });
      if(baseUrl){ var r = withoutPhotos(engine.toRecipe("")); delete r.cast; out.link = baseUrl + "#recipe=" + b64url(JSON.stringify(r)); }
      return out;
    }
    function withoutPhotos(r){
      (r.cast || []).forEach(function(p){ if(p.photo) p.photo = true; });
      return r;
    }
    function b64url(s){
      var b = typeof Buffer !== "undefined" ? Buffer.from(s, "utf8").toString("base64") : btoa(unescape(encodeURIComponent(s)));
      return b.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    }

    /* ---------------- manifest ---------------- */
    function manifest(extra){
      var c = caps(), m = model();
      var doc = {
        schema: SCHEMA,
        name: "Prompt Bench",
        bench: c.bench,
        purpose: "Builds image-generation prompts that leave the image model nothing to invent: the cast is stated as complete, style comes before people, gaps become questions, and a shareable version strips out every real person.",
        steps: [
          "Read the client's request. Put their own words in 'brief'.",
          "Add anything you know for certain: the cast (names, what makes each recognisable), a master, explicit modules.",
          "Call compose. It fills empty lanes from the brief and never overrides what you set.",
          "Read 'gaps'. Blockers must be answered; 'should' items are worth asking. 'questions' is a ready-made message for the client.",
          "Answer by sending compose again with the same brief plus the answers in recipe or cast.",
          "Give 'prompt' to the image model. Give 'shareable' to anyone else: no names, no photos, no private packs."
        ],
        rules: [
          "Explicit choices always win. Suggestions only fill lanes you left empty.",
          "Modules are addressed by their exact wording, or by number for the current pack set. Numbers move when packs change; wording does not.",
          "A cast given to compose is the whole cast. Nobody else is added.",
          "cast[i].photo: true means a reference photo will be attached to the image model's message. The prompt then says so; without it the prompt asks for one.",
          "Write text boxes as what is there, not what is not. Put genuine bans in the keep-out field, which is capped.",
          "The same recipe and seed always give the same prompt."
        ],
        compose: {
          input: {
            brief: "string. The client's own words, untouched.",
            cast: "array of { name, kind: 'person'|'animal', " + m.castFields.map(function(f){ return f.key; }).join(", ") + ", desc, photo: boolean }. Optional.",
            recipe: "partial recipe: { master, modules: [wording or number], castCount, dials: {id: value}, fields: {id: text}, strangers, castOpen, discipline, askQuestions, askCount, mediumHold, seed }. Optional.",
            fill: "'empty' (default) fills lanes the recipe left empty from the brief; 'none' uses only what you set.",
            context: "string. Who these people are to each other. Optional.",
            discipline: "boolean, default true: the anatomy and continuity block."
          },
          output: "{ prompt, followup, shareable, recipe, decisions[], gaps[], questions, shareableLeaks[], ready, words, link? }"
        },
        castFields: m.castFields.map(function(f){ return { key: f.key, label: f.label, hint: f.hint || "" }; }),
        masters: m.masters.map(function(x){ return { id: x.id, name: x.name, blurb: x.blurb || "", castSizes: Object.keys(x.alt || {}) }; }),
        categories: m.categories.map(function(x){ return { key: x.key, label: x.label, note: x.note || "", modules: x.items.length, printedFirst: styleKeys().indexOf(x.key) > -1 }; }),
        dials: c.dials,
        fields: m.fields.map(function(f){ return { id: f.id, label: f.label, hint: f.hint || "", section: f.section || "", keepOut: !!f.attachTo, limit: f.limit || null }; }),
        maxCast: c.maxCast,
        requirePhoto: settings().requirePhoto !== false,
        modules: c.modules,
        gapLevels: { blocker: "must be answered before the prompt is trustworthy", should: "worth asking the client", could: "optional detail", note: "information only" }
      };
      if(extra) Object.keys(extra).forEach(function(k){ doc[k] = extra[k]; });
      return doc;
    }

    return { manifest: manifest, suggest: suggest, gaps: gaps, questions: questionsText, compose: compose, leakScan: leakScan, tokens: tokens };
  }

  return { createAgent: createAgent, SCHEMA: SCHEMA, tokens: tokens };
});
