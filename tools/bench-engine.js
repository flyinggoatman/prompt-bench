/* ------------------------------------------------------------------
   Prompt Bench engine.

   GENERATED. Do not edit: run .github/build-engine.py, which lifts these
   functions verbatim out of prompt-bench.html. The page and this module are
   therefore the same assembler rather than two that agree for a while.

   Usage:

     const { createBench } = require("./bench-engine.js");
     const bench = createBench({ packs, profile });
     bench.setState({ master: "A", on: { 12: true }, castCount: 1 });
     bench.assemble();            // the whole prompt
     bench.assemble("followup");  // the edit instruction
     bench.assemble("shareable"); // the version for somebody else

   Everything here reads the merged model and a state object. Nothing here
   reads a page, a browser or a disk.
   ------------------------------------------------------------------ */
"use strict";

function createBench(options){
  options = options || {};

  var PROFILE = options.profile || { bench: "main", keyPrefix: "promptbench", borrow: null };
  var BUILT_IN = options.builtIn || { pack: "Built in" };
  var loadedPacks = (options.packs || []).slice();
  var serverPacks = [];
  var MODEL = null;
  var MAX_CAST = 5;
  var seed = 1;
  var publicMode = false;
  var _masterId = null;
  /* The remembered cast baseline is a private build capability of the page.
     Outside the page there is none, and the engine copes with that exactly as
     a public build does. */
  var privateCastRestore = null;
  var state = { on:{}, dials:{}, fields:{}, cast:[], castCount:null, master:null,
                discipline:false, followup:false, strangers:false, castOpen:false,
                askQuestions:true, askCount:4, mediumHold:8 };

  var BUILT_IN_WORDING = {
    castHeading: "CAST",
    castWithPhotos: "Reference photographs are attached for identity only. Read them to learn who these people are and what makes each of them recognisable. Do not read them for how to draw. Every face in this image is built in the style set out above, by the same hand and with the same marks as the room around it, and is never copied, traced or rendered from the photograph. Identify each character by their signifiers rather than by exact facial likeness. A photographic or half photographic face in a drawn scene is wrong even when the likeness is perfect, and a good likeness is no reason to keep one.",
    castWithoutPhotos: "Identify each character by their signifiers. Every face is built in the style set out above, by the same hand and with the same marks as the room around it.",
    askHeading: "BEFORE YOU DRAW",
    askOn: "Interview me first. Ask {q} question{qs} before you draw anything, in one interaction, using this platform's own interactive controls where it has them: single choice where the options exclude each other, multi select where several can apply, free text where a fact cannot safely be guessed. Prefer asking to assuming. Any detail that would change the picture and is not settled below is worth a question, and the {q} question{qs} should be the ones that change it most. Ask them all at once, phrased to be read on a phone, wait for the answers, and treat what comes back as decided. Do not ask fewer than {q} and do not run a second questionnaire afterwards.",
    askOff: "Ask nothing. Do not offer questions, options, a questionnaire or a check that you have understood. Anything this brief does not settle is yours to decide, so decide it and keep going. Draw the image in your first reply.",
    mediumNoReference: "No reference photograph is attached, so the medium decides everything. Faces are made the same way, and to the same standard, as everything else in the frame.",
    mediumAbsolute: "The medium is absolute. The reference is read for identity only and never for rendering: nothing of the photograph's surface, lighting, focus or grain reaches the drawing. A face is built from the same marks as the wall behind it.",
    mediumLeads: "The medium leads. Take the likeness from the reference and take everything about how it is made from the medium above. Where the two disagree, the medium wins.",
    mediumEven: "An even hold. Follow the reference for proportion and the set of the features, and the medium for surface, colour and mark making. Neither wins outright, and the face still belongs to the same drawing as the room around it.",
    mediumReferenceLeads: "The reference leads. Follow the photograph closely for proportion, detail and the way light falls on the face, and let the medium show mainly in surface, colour and the visible marks of the tool. This is still a picture made by hand rather than a photograph.",
    mediumReferenceGoverns: "The reference governs the face. Follow the photograph closely, modelling and detail included, and keep only as much of the medium as survives that. Everything else in the frame stays fully in the medium, and the two must read as one picture rather than a face pasted into a drawing.",
    styleHeading: "HOW THIS IS DRAWN",
    styleRule: "That is the style of the whole picture, decided before anybody in it is described. Everything below says what to draw, never how: no part of it changes the style above, and nothing in it is rendered more literally than anything else. People are drawn to exactly the same standard as the objects beside them.",
    outfitRule: "Outfits change in every image within these descriptions. Never repeat an exact outfit.",
    missingPhotoOne: "No reference photo is provided for {names}. Before you draw anything, ask me for a photo of them and for one recognisable marker to identify them by. Do not invent an appearance.",
    missingPhotoMany: "No reference photo is provided for {names}. Before you draw anything, ask me for a photo of each of them and for one recognisable marker to identify them by. Do not invent an appearance.",
    noPhotoOne: "No reference photograph is attached, and none is needed. Build {names} from the description above. Keep the result consistent if they are drawn again.",
    noPhotoMany: "No reference photographs are attached, and none are needed. Build {names} from the descriptions above. Keep each of them consistent if they are drawn again.",
    castAnyone: "somebody",
    publicUploadOffer: " Offer image upload where a reference picture would change the result and none has been supplied.",
    publicLaterImages: " If reference images arrive afterwards and something is still open, ask again once at that point, in the same way.",
    publicPhotoOwner: " If a reference photo is attached, say who it is of.",
    descriptionOpen: "{NAME}.",
    listTwo: "{a} and {b}",
    listMany: "{list} and {last}",
    castSizeExact: "This image has exactly {N} character{s}: {cast}. The cast described below is the complete list.",
    castSizeOne: "This image has exactly one character: {cast}. The cast described below is the complete list.",
    castSizeNone: "No specific characters are established for this image. Whoever appears is yours to decide from the brief below.",
    castSizeOpen: "This image starts with {N} character{s}: {cast}. Ask whether anybody else should appear, and offer a way to say nobody else.",
    strangersNone: "Everybody visible in the image belongs to the cast above.",
    strangersAllowed: "Other figures may appear as unnamed background presence: passers by, a queue, people at other tables. They stay strangers, drawn generically, never named, never described as characters and never somebody to ask about.",
    photosOne: "One reference photograph is attached. It is of {names}.",
    photosSomeOfOne: "{count} reference photographs are attached. They are all of {names}, from different angles and occasions.",
    photosMany: "{count} reference photographs are attached, covering {names}.",
    photosComplete: "Those are the complete reference set for this image. Any other image in this conversation belongs to other work and is unrelated to this prompt.",
    thisImageHeading: "THIS IMAGE",
    moduleLine: "{LABEL}: {v}",
    dialsHeading: "DIALS",
    variationHeading: "VARIATION",
    defaultSection: "ALSO",
    followUpOpen: "Keep the previous image exactly as it is: same characters, same style, same palette, same composition. Change only the following.",
    followUpItem: "- {v}",
    followUpClose: "Do not redraw anything else. Do not change anyone's face, clothing or position unless listed above.",
    disciplineHeading: "GETTING THE DETAILS RIGHT",
    publicContext: "FILLING IN FROM WHAT YOU ALREADY KNOW\nUse the conversation you are already in. Anything the person has said, asked for or attached earlier is yours to use, and a detail you can reasonably take from it is better filled in than asked about. Where a creative choice is yours to make and nobody has asked to make it themselves, make it.\n\nFacts about people are different. Fill in what the conversation genuinely supports, then show the person what you have filled in as a short readable list and ask, in one question, whether you have it right. Offer them a way to confirm and a way to say something is wrong. Ask this once, and wait for the answer before generating anything.\n\nIf they confirm, carry on, and let what they confirmed shape whatever you ask next rather than asking the same thing again in another form. If they say something is wrong, ask about that part in ordinary conversation in the same thread, change only the part they corrected, and keep everything they confirmed. A detail nobody has supplied, and that the conversation does not support, stays a question or stays a placeholder rather than becoming an invention.",
    publicCastIntro: "Replace everything inside square brackets. Leave a line as it is and I will ask you about it, or choose it myself if you would rather not decide.",
    publicCastWhoPerson: "{id} is a person.",
    publicCastWhoAnimal: "{id} is an animal.",
    publicCastName: "Name: [optional. Leave this out and I will keep calling them {id}.]",
    publicCastField: "{label}: [{hint}]",
    publicCastRepeat: "Add {next}, and any others, in the same shape. An animal has no clothing line.{photoOwner}",
    publicCastComplete: "That is the whole cast. An animal has no clothing line.{photoOwner} Everybody in the image is listed above, so treat the list as finished and fill in the brackets rather than adding anybody.",
    publicCharactersOpen: "You do not know in advance how many characters there will be. Ask who else should appear and offer a way to say nobody else. If several are described at once, split them into sequential identifiers yourself, so two named people and one unnamed animal become Person_2 and Person_3 carrying their names and Person_4 with no name. Adding a character is your own bookkeeping, not something the interface does.",
    publicWhenToAsk: "WHEN TO ASK\nRun that single interaction in your first reply, using the platform's own controls, before generating anything.{laterImages} Where the brief already answers everything, generate and say nothing.",
    publicAskHowMany: "One of those questions is how many characters the image has. Offer it as a single choice with a way to say only the one described below, and treat the answer as settled for the rest of the conversation.",
    publicIntro: "HOW TO RUN THIS PROMPT\nBefore generating anything, decide whether information essential to the image is genuinely missing. If the brief below is already enough, or the person tells you to decide, make the image and do not interview them.\n\nWhen you do need something, ask for it using this platform's own native interactive input or questionnaire controls if it has any: single choice for options that exclude each other, multi select where several answers can apply, free text for facts that cannot safely be guessed, visual selection only where the platform supplies real previews.{uploadOffer} Use only controls this platform actually provides, and never invent previews, asset names or capabilities it does not have. Allow a custom answer alongside the suggested ones where that helps. If there are no native controls at all, ask the same questions in ordinary conversation.\n\nPut everything you already know you need into a single interaction of {q} short question{qs}, phrased to be read on a phone. Do not ask fewer, and do not run one questionnaire after another. Where a later question genuinely depends on an earlier answer, ask that one as an ordinary conversational follow up instead. Never ask for anything already supplied, and never show internal tool names, schemas or raw answer data to the person. Wait for the answers before generating, and treat what comes back as authoritative.",
    publicCharacters: "WHO IS IN THE IMAGE\nEveryone in the image, whether a person or an animal, has a stable identifier: Person_1, Person_2, Person_3 and so on. Person_1 is the main subject. The word Person is only a label; Person_2 may perfectly well be a dog, a cat or a horse.\n\nA name is optional. When a name is given, attach it to the identifier rather than replacing it, so Person_1 keeps that label and carries the name as well. Never invent a name for somebody who was not given one; an unnamed character simply stays Person_3.\n\nThe cast section below is a blank form. Every square bracket is a placeholder to replace. Whoever is running this can fill them in directly, or leave them alone and be asked. Treat anything still in square brackets as unanswered: ask about it, or decide it yourself if they have said you should. Never draw a character from a placeholder as though it were a description.\n\nCollect only what changes the picture. Do not make anyone fill in fields the image does not need, and do not ask again for anything already supplied."
  };

  var BUILT_IN_SETTINGS = { maxCast: 5, variationPools: 3, requirePhoto: true,
                            styleFirst: ["MEDIUM", "FINISH", "PALETTE", "LIGHT"],
                            minQuestions: 1, maxQuestions: 8, defaultQuestions: 4,
                            defaultMediumHold: 8 };

  var BUILT_IN_CAST_FIELDS = [
    { key:"marker", label:"Signifier", hint:"The one thing always present. This is what makes them recognisable, not their face.",
      line:"Constant in every image: {v}.", order:10, promptOrder:40 },
    { key:"looks", label:"Appearance", hint:"Build, hair, age, how they carry themselves.",
      line:"{v}.", order:20, promptOrder:10 },
    { key:"wears", label:"Clothing", hint:"What they actually reach for, not one fixed outfit.",
      line:"{v}.", order:30, promptOrder:20, outfitRule:true },
    { key:"manner", label:"Manner", hint:"How they behave around the others.",
      line:"{v}.", order:40, promptOrder:30 },
    { key:"likes", label:"Interests", hint:"Shown as objects in the scene, never as a label.",
      line:"Interested in {v}, which may show up as objects in the scene rather than as a label.", order:50, promptOrder:50 },
    { key:"avoid", label:"Never draw them with", hint:"Specific to this character. Keep it short.",
      line:"Never draw {name} with {v}.", order:60, promptOrder:60 }
  ];

  var BUILT_IN_DISCIPLINE = [
    { id:"count", order:10, text:"Count the picture before finishing it. The number of people, the anatomy of each one and the number of every named object match what this prompt, the character descriptions and any reference material establish." },
    { id:"limbs", order:20, text:"Each human figure has the anatomy their description or reference establishes. Where nothing else is established, that is one head on one neck, two arms and two legs, each arm beginning at a shoulder and each leg beginning at a hip, and each limb staying joined to one person along its whole length. Where a limb difference, an amputation, a prosthesis or another physical difference is established, that is what the picture shows, accurately and consistently." },
    { id:"hands", order:30, text:"Each hand follows the anatomy established for that character. Where an ordinary hand is intended, that is four fingers and one thumb arranged naturally. A hand holding something closes around it in a grip that works, so it is plain what is held and which hand holds it." },
    { id:"face", order:40, text:"Each face keeps the features its description or reference establishes. Where an ordinary human face is intended, that is two eyes level with one another, one nose, one mouth and two ears set coherently on the head. Teeth that show suit the character, the expression and the angle." },
    { id:"pairs", order:50, text:"Paired things stay true to their established design: the two shoes of one pair match each other, sleeves belong to their garment, a pair of glasses keeps its lenses, one set of headphones keeps its earpieces. Asymmetry that the prompt or a reference establishes is deliberate and stays." },
    { id:"singular", order:60, text:"Each object appears in the number this prompt establishes. One of something stays one identifiable object throughout, and where several are called for they stay that many, each keeping its own identity. Track who holds or owns each one and where it sits, so a phone, a mug, a bag, a set of keys, a pair of glasses, headphones or a cable remains the same object wherever it appears in the scene." },
    { id:"attached", order:70, text:"Straps, cables, handles and the like follow paths that work. A strap follows the body and the thing it carries, a cable runs between the two ends it connects, a handle stays joined to whatever it lifts, and every visible attachment point meets the object it belongs to." },
    { id:"separate", order:80, text:"Every person and every object keeps a coherent form of its own. Where forms overlap, depth and occlusion make plain which is in front and which continues behind. Clothing stays on its wearer, hair stays on its character, and each thing stays distinguishable from the others and from the background." },
    { id:"contact", order:90, text:"Anything resting on or held up by something meets it in a way that works. Objects on a table make contact with the tabletop, feet meet the ground as the pose requires, a seated body is carried by its seat, and weight is borne by whatever sits underneath it." },
    { id:"fits", order:92, text:"Everything occupies a space that could hold it. A case, box, vehicle, doorway, seat, frame or enclosure is drawn large enough for whatever is shown inside it, with room at the edges, and anything shown inside one is small enough to be there. Where somebody or something is larger than the space the prompt names, they are drawn beside it, behind it, leaning over it or reaching into it, whichever the scene supports. Where the prompt, a character description or a reference establishes a deliberate impossibility, that is what the picture shows." },
    { id:"proportion", order:94, text:"Sizes agree with one another inside the frame. People, furniture, doorways, vehicles, animals, plants and handheld objects keep the relative sizes they would really have, so a mug reads as a mug against a hand, a bench as a bench against a person, and a room as a room against the people standing in it. Where a description or reference establishes something unusually large or small, it keeps that established size wherever it appears." },
    { id:"light", order:100, text:"Lighting stays consistent with the light sources the image establishes. Each visible shadow agrees with the position, direction and quality of the light that casts it, and where several sources are established their combined effect stays coherent." },
    { id:"sameness", order:110, text:"Across panels, cells, frames or views, each character keeps the identity, anatomy, face, hair, build, clothing and established physical differences they began with, and each recurring object keeps its design and colour, until the story changes one of them." },
    { id:"persistence", order:120, text:"Across those panels the established number, scale, orientation, depth and relative position of people and objects all hold. When the viewpoint changes they are drawn from the new viewpoint with those same relationships intact." },
    { id:"consequence", order:130, text:"Changes between panels follow events in the story. An object nobody has touched keeps the state and the place it had. Something set down stays where it was put, something picked up travels with whoever carries it, something dropped lies where it fell, and a deliberate change persists from the moment it happens." }
  ];

  var NEGATIVE_PHRASING = /\b(do not|don't|never|avoid|avoiding|must not|should not|cannot|can't|refrain|no extra|without any)\b/i;

  var NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];

  function tpl(s, map){
    return String(s === undefined || s === null ? "" : s).replace(/\{(\w+)\}/g, function(whole, k){
      return Object.prototype.hasOwnProperty.call(map, k) ? map[k] : whole;
    });
  }

  function say(key, map){
    var w = (MODEL && MODEL.wording) || BUILT_IN_WORDING;
    var s = w[key] === undefined ? BUILT_IN_WORDING[key] : w[key];
    var m = photoClauses(), k;
    if(map){ for(k in map){ if(Object.prototype.hasOwnProperty.call(map, k)) m[k] = map[k]; } }
    return fill(tpl(s, m));
  }

  function castFieldList(byPrompt){
    var list = ((MODEL && MODEL.castFields) || BUILT_IN_CAST_FIELDS).slice();
    list.sort(function(a, b){
      var k = byPrompt ? "promptOrder" : "order";
      var ao = a[k] === undefined ? (a.order === undefined ? 999 : a.order) : a[k];
      var bo = b[k] === undefined ? (b.order === undefined ? 999 : b.order) : b[k];
      return ao - bo;
    });
    return list;
  }

  function packBench(p){
    if(p.bench) return p.bench;
    var d = p.data || {};
    if(d.bench === "main" || d.bench === "persona" || d.bench === "both") return d.bench;
    var path = String(p.path || "").replace(/\\/g, "/");
    return path.indexOf("persona-packs/") > -1 ? "persona" : "main";
  }

  function scopePack(p){
    var mine = PROFILE.bench, theirs = packBench(p);
    if(theirs === mine || theirs === "both") return p;
    if(!PROFILE.borrow || !PROFILE.borrow.length) return null;
    var d = p.data || {}, keep = [];
    (d.categories || []).forEach(function(c){
      if(PROFILE.borrow.indexOf(c.key) > -1) keep.push(c);
    });
    if(!keep.length) return null;
    return { name: p.name, path: p.path, borrowed: true,
             data: { pack: d.pack, private: d.private, categories: keep } };
  }

  function allPacks(){
    var raw = [{ name:"Built in", path:"built-in", data:BUILT_IN, bench:PROFILE.bench }]
                .concat(serverPacks, loadedPacks);
    var out = [];
    raw.forEach(function(p){
      var scoped = scopePack(p);
      if(scoped) out.push(scoped);
    });
    return out;
  }

  function publicPacks(){
    return allPacks().filter(function(p){ return !(p.data && p.data.private); });
  }

  function mergeById(list, incoming, key){
    incoming.forEach(function(item){
      var found = -1;
      for(var i=0;i<list.length;i++){ if(list[i][key] === item[key]){ found = i; break; } }
      if(found > -1){
        var merged = {}, k;
        for(k in list[found]) merged[k] = list[found][k];
        for(k in item) merged[k] = item[k];
        list[found] = merged;
      } else { list.push(item); }
    });
  }

  function mergeCategories(list, incoming){
    incoming.forEach(function(inc){
      var found = null;
      for(var i=0;i<list.length;i++){ if(list[i].key === inc.key){ found = list[i]; break; } }
      if(!found){
        found = { key:inc.key, label:inc.label || inc.key, note:inc.note || "",
                  order:(inc.order === undefined ? 999 : inc.order), items:[] };
        list.push(found);
      }
      if(inc.label !== undefined) found.label = inc.label;
      if(inc.note !== undefined) found.note = inc.note;
      if(inc.order !== undefined) found.order = inc.order;
      if(inc.replace) found.items = [];
      (inc.items || []).forEach(function(it){
        var dup = null, k;
        for(var j=0;j<found.items.length;j++){ if(found.items[j].t === it.t){ dup = found.items[j]; break; } }
        if(dup){
          String(it.m || "").split("").forEach(function(ch){ if(dup.m.indexOf(ch) < 0) dup.m += ch; });
          /* A later pack may add settings to a module it did not write, so
             everything except the wording and the master list is carried over. */
          for(k in it) if(k !== "m" && k !== "t") dup[k] = it[k];
        } else {
          /* Copy the whole item rather than the wording alone: needs, alt,
             strangers and anything a future pack format adds all travel with it. */
          var copy = {};
          for(k in it) copy[k] = it[k];
          copy.m = it.m || "ABC";
          copy.t = it.t;
          found.items.push(copy);
        }
      });
    });
  }

  function modelFrom(packs){
    var m = { shared:[], masters:[], categories:[], dials:[], variation:[], fields:[], people:[],
              wording:{}, settings:{}, castFields:[], discipline:[] };
    var k;
    for(k in BUILT_IN_WORDING) m.wording[k] = BUILT_IN_WORDING[k];
    for(k in BUILT_IN_SETTINGS) m.settings[k] = BUILT_IN_SETTINGS[k];
    BUILT_IN_CAST_FIELDS.forEach(function(f){
      var copy = {}, j;
      for(j in f) copy[j] = f[j];
      m.castFields.push(copy);
    });
    BUILT_IN_DISCIPLINE.forEach(function(d){
      var copy = {}, j;
      for(j in d) copy[j] = d[j];
      m.discipline.push(copy);
    });
    packs.forEach(function(p){
      var d = p.data || {};
      if(d.shared)     mergeById(m.shared, d.shared, "id");
      if(d.masters)    mergeById(m.masters, d.masters, "id");
      if(d.people)     mergeById(m.people, d.people, "id");
      if(d.categories) mergeCategories(m.categories, d.categories);
      if(d.dials)      mergeById(m.dials, d.dials, "id");
      if(d.variation)  mergeById(m.variation, d.variation, "id");
      if(d.fields)     mergeById(m.fields, d.fields, "id");
      if(d.castFields) mergeById(m.castFields, d.castFields, "key");
      if(d.discipline) mergeById(m.discipline, d.discipline, "id");
      if(d.wording)    for(var wk in d.wording) m.wording[wk] = d.wording[wk];
      if(d.settings)   for(var sk in d.settings) m.settings[sk] = d.settings[sk];
    });
    m.castFields = m.castFields.filter(function(f){ return !f.drop; });
    m.discipline = m.discipline.filter(function(d){ return !d.drop; });
    var byOrder = function(a,b){
      var ao = a.order === undefined ? 999 : a.order;
      var bo = b.order === undefined ? 999 : b.order;
      return ao - bo;
    };
    m.categories.sort(byOrder); m.dials.sort(byOrder); m.discipline.sort(byOrder);
    m.variation.sort(byOrder); m.fields.sort(byOrder);
    var n = 0;
    m.categories.forEach(function(c){ c.items.forEach(function(it){ n++; it.n = n; it.cat = c.key; }); });
    m.count = n;
    var cap = parseInt(m.settings.maxCast, 10);
    if(isNaN(cap)) cap = BUILT_IN_SETTINGS.maxCast;
    m.settings.maxCast = Math.max(1, Math.min(9, cap));
    var pools = parseInt(m.settings.variationPools, 10);
    m.settings.variationPools = isNaN(pools) ? BUILT_IN_SETTINGS.variationPools : Math.max(0, pools);
    /* A bench that draws somebody from a description rather than reproducing a
       real person has nothing to reference, so a named character without a photo
       is the ordinary case there rather than something to stop and ask about. */
    m.settings.requirePhoto = (m.settings.requirePhoto === undefined)
      ? BUILT_IN_SETTINGS.requirePhoto : (m.settings.requirePhoto !== false);
    if(!Array.isArray(m.settings.styleFirst)) m.settings.styleFirst = BUILT_IN_SETTINGS.styleFirst;
    return m;
  }

  function buildModel(){
    MODEL = modelFrom(allPacks());
    MAX_CAST = MODEL.settings.maxCast;
  }

  function blankPerson(){
    var p = { name:"", kind:"person", photo:"", desc:"" };
    castFieldList().forEach(function(f){ p[f.key] = ""; });
    return p;
  }

  function seedCast(fromPacks){
    var src = fromPacks ? castSourceList() : [];
    var out = [];
    for(var i=0;i<MAX_CAST;i++){
      if(src[i]){
        var p = blankPerson(), k;
        for(k in src[i]) if(k in p) p[k] = src[i][k] || "";
        p.kind = src[i].kind || "person";
        out.push(p);
      } else { out.push(blankPerson()); }
    }
    return out;
  }

  function ensureDials(){
    if(!MODEL || !MODEL.dials) return;
    MODEL.dials.forEach(function(d){
      if(state.dials[d.id] === undefined){
        state.dials[d.id] = (d.value === undefined ? (d.min === undefined ? 0 : d.min) : d.value);
      }
    });
  }

  function ensureCast(){
    if(!state.cast || !state.cast.length) state.cast = seedCast(true);
    while(state.cast.length < MAX_CAST) state.cast.push(blankPerson());
    if(state.castCount === null || state.castCount === undefined){
      state.castCount = Math.min(castSourceList().length, MAX_CAST);
    }
    if(state.castCount > MAX_CAST) state.castCount = MAX_CAST;
    if(state.castCount < 0) state.castCount = 0;
  }

  function activeCast(){ return state.cast.slice(0, state.castCount); }
  
  /* Whether a named character with no photo is a gap to ask about. True on the
     main bench, where the cast are real people being reproduced. False where a
     pack turns it off, as Persona Bench does: there the modules are the
     likeness, so demanding a photograph stops the work for nothing. */
  function requirePhoto(){
    return !(MODEL && MODEL.settings && MODEL.settings.requirePhoto === false);
  }

  function requirePhoto(){
    return !(MODEL && MODEL.settings && MODEL.settings.requirePhoto === false);
  }

  function castSourceList(){
    if(MODEL && MODEL.people && MODEL.people.length) return MODEL.people;
    return privateCastRestore ? privateCastRestore.baseline() : [];
  }

  function castSize(){
    var n = parseInt(state.castCount, 10);
    if(isNaN(n) || n < 0) n = 0;
    return Math.min(n, MAX_CAST);
  }

  function castNames(){
    var n = castSize(), out = [], i;
    for(i = 0; i < n; i++){
      /* A shareable prompt speaks in identifiers, because the person running it
         has not met anybody. This page speaks in names, and an unnamed slot is
         somebody rather than Person_3: the identifier would be a placeholder
         nobody had asked for. */
      if(publicMode){ out.push("Person_" + (i+1)); continue; }
      var p = state.cast[i] || {};
      out.push((p.name || "").trim() || "somebody");
    }
    return out;
  }

  function joinPlain(a){
    if(!a.length) return "";
    if(a.length === 1) return a[0];
    return a.slice(0, -1).join(", ") + " and " + a[a.length - 1];
  }

  function listNames(a){
    if(a.length === 1) return a[0];
    if(a.length === 2) return say("listTwo", { a: a[0], b: a[1] });
    return say("listMany", { list: a.slice(0,-1).join(", "), last: a[a.length-1] });
  }

  function word(key, fallback){
    var w = (MODEL && MODEL.wording) || BUILT_IN_WORDING;
    var s = w[key] === undefined ? BUILT_IN_WORDING[key] : w[key];
    return String(s === undefined || s === null ? fallback : s);
  }

  function anyoneWord(){ return word("castAnyone", "somebody"); }
  
  /* {n} gives the digit, which suits a line of instruction. {N} gives the word,
     which is what prose wants: "three faces at three stages" rather than "3
     faces at 3 stages". Past nine it falls back to the digit. */
  var NUMBER_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
  function numberWord(n){
    n = parseInt(n, 10);
    if(isNaN(n) || n < 0) return "0";
    return NUMBER_WORDS[n] === undefined ? String(n) : NUMBER_WORDS[n];
  }

  function numberWord(n){
    n = parseInt(n, 10);
    if(isNaN(n) || n < 0) return "0";
    return NUMBER_WORDS[n] === undefined ? String(n) : NUMBER_WORDS[n];
  }

  function photoClauses(){
    var on = requirePhoto();
    return {
      uploadOffer: on ? word("publicUploadOffer", "") : "",
      laterImages: on ? word("publicLaterImages", "") : "",
      photoOwner:  on ? word("publicPhotoOwner", "")  : ""
    };
  }

  function fill(text){
    var n = castSize(), names = castNames();
    var out = String(text).replace(/\{([1-9])\}/g, function(whole, d){
      var i = parseInt(d, 10);
      if(i <= n) return names[i-1];
      return publicMode ? "Person_" + d : "somebody";
    });
    return out
      .replace(/\{n\}/g, String(n))
      .replace(/\{N\}/g, numberWord(n))
      .replace(/\{q\}/g, String(askCount()))
      .replace(/\{qs\}/g, askCount() === 1 ? "" : "s")
      .replace(/\{cast\}/g, joinPlain(names) || anyoneWord())
      .replace(/\{s\}/g, n === 1 ? "" : "s")
      .replace(/\{they\}/g, n === 1 ? "they" : "they")
      .replace(/\{them\}/g, n === 1 ? "them" : "them")
      .replace(/\{their\}/g, "their")
      .replace(/\{is\}/g, n === 1 ? "is" : "are");
  }

  function tokens(){
    var map = {};
    activeCast().forEach(function(p,i){
      map[String(i+1)] = (p.name || "").trim() || "somebody";
    });
    return map;
  }

  function needsOf(it){
    if(it.needs !== undefined){
      var n = parseInt(it.needs, 10);
      if(!isNaN(n)) return Math.max(0, n);
    }
    var high = 0;
    String(it.t || "").replace(/\{([1-9])\}/g, function(whole, d){
      var v = parseInt(d, 10);
      if(v > high) high = v;
      return whole;
    });
    return high;
  }

  function textOf(it){
    var n = castSize();
    if(it.alt && needsOf(it) > n){
      var key = String(n);
      if(typeof it.alt[key] === "string") return it.alt[key];
    }
    return it.t;
  }

  function masterBody(m){
    var n = castSize();
    if(m && m.alt && typeof m.alt[String(n)] === "string") return m.alt[String(n)];
    return (m && m.body) || "";
  }

  function fitsCast(it){
    if(it.strangers === true && !state.strangers) return false;
    var n = castSize();
    if(needsOf(it) <= n) return true;
    return !!(it.alt && typeof it.alt[String(n)] === "string");
  }

  function suits(it, mid){
    if(!fitsCast(it)) return false;
    return suitsMaster(it, mid);
  }

  function suitsMaster(it, mid){
    if(it.m.indexOf(mid) > -1 || it.m.indexOf("*") > -1) return true;
    for(var i=0;i<MODEL.masters.length;i++){
      var m = MODEL.masters[i];
      if(m.id === mid && m.inherits && it.m.indexOf(m.inherits) > -1) return true;
    }
    return false;
  }

  function hiddenByCast(mid){
    var n = 0;
    MODEL.categories.forEach(function(c){
      c.items.forEach(function(it){
        if(suitsMaster(it, mid) && !fitsCast(it)) n++;
      });
    });
    return n;
  }

  function currentMasterId(){
    var want = state.master || _masterId;
    if(want){
      for(var i=0;i<MODEL.masters.length;i++) if(MODEL.masters[i].id === want) return want;
    }
    return MODEL.masters.length ? MODEL.masters[0].id : null;
  }

  function selected(){
    var mid = currentMasterId(), out = [];
    MODEL.categories.forEach(function(c){
      c.items.forEach(function(it){
        if(state.on[it.n] && suits(it, mid)) out.push({cat:c, it:it});
      });
    });
    return out;
  }

  function dialText(d, v){
    var stops = d.stops || [];
    for(var i=0;i<stops.length;i++){
      if(v <= stops[i].upTo) return fill(String(stops[i].text).replace(/\{v\}/g, v));
    }
    return stops.length ? fill(String(stops[stops.length-1].text).replace(/\{v\}/g, v)) : "";
  }

  function pickVariation(){
    var r = seed, out = [], pools = MODEL.variation.slice();
    var chosen = [];
    while(pools.length && chosen.length < MODEL.settings.variationPools){
      r = (r * 1103515245 + 12345) % 2147483648;
      chosen.push(pools.splice(Math.abs(r) % pools.length, 1)[0]);
    }
    chosen.sort(function(a,b){ return (a.order===undefined?999:a.order) - (b.order===undefined?999:b.order); });
    chosen.forEach(function(pool,i){
      r = (r * 1103515245 + 12345 + i*7919) % 2147483648;
      var opts = pool.options || [];
      if(opts.length) out.push(fill(opts[Math.abs(r) % opts.length]));
    });
    return out;
  }

  function fieldValue(f){
    var v = (state.fields[f.id] || "").trim();
    if(!v) return "";
    if(f.splitList){
      var items = v.split(/[,\n]/).map(function(s){return s.trim();}).filter(Boolean);
      if(f.limit) items = items.slice(0, f.limit);
      if(!items.length) return "";
      v = items.join(", ");
    }
    return fill(String(f.wrap || "{v}").replace(/\{v\}/g, v));
  }

  function composeDescription(p){
    var name = (p.name || "").trim();
    if(!name) return "";
    var map = { name: name, NAME: name.toUpperCase() };
    var parts = [ say("descriptionOpen", map) ];
    castFieldList(true).forEach(function(f){
      var v = (p[f.key] || "").trim().replace(/[.\s]+$/, "");
      if(!v) return;
      parts.push(fill(tpl(f.line === undefined ? "{v}." : f.line,
        { v: v, name: name, NAME: map.NAME })));
    });
    return parts.join(" ").trim();
  }

  function askCount(){
    var lo = (MODEL && MODEL.settings && MODEL.settings.minQuestions) || BUILT_IN_SETTINGS.minQuestions;
    var hi = (MODEL && MODEL.settings && MODEL.settings.maxQuestions) || BUILT_IN_SETTINGS.maxQuestions;
    var n = parseInt(state.askCount, 10);
    if(isNaN(n)) n = BUILT_IN_SETTINGS.defaultQuestions;
    return Math.max(lo, Math.min(hi, n));
  }

  function asksQuestions(){ return state.askQuestions !== false; }
  
  function askBlock(){
    return say("askHeading") + "\n" + say(asksQuestions() ? "askOn" : "askOff");
  }

  function askBlock(){
    return say("askHeading") + "\n" + say(asksQuestions() ? "askOn" : "askOff");
  }

  function mediumHold(){
    var n = parseInt(state.mediumHold, 10);
    if(isNaN(n)) n = BUILT_IN_SETTINGS.defaultMediumHold;
    return Math.max(0, Math.min(10, n));
  }

  function hasReference(){
    if(publicMode) return true;   /* a form: a photograph may well be attached to it */
    return activeCast().some(function(p){ return !!p.photo; });
  }

  function mediumHoldKey(){
    /* Left is the reference, right is the medium: the slider reads as how much
       of the medium survives, so pushing it right gets you more of the drawing. */
    var n = mediumHold();
    if(n <= 1) return "mediumReferenceGoverns";
    if(n <= 3) return "mediumReferenceLeads";
    if(n <= 5) return "mediumEven";
    if(n <= 8) return "mediumLeads";
    return "mediumAbsolute";
  }

  function mediumHoldLine(){
    return say(hasReference() ? mediumHoldKey() : "mediumNoReference");
  }

  function styleFirstKeys(){
    var keys = (MODEL && MODEL.settings && MODEL.settings.styleFirst);
    return Array.isArray(keys) ? keys : BUILT_IN_SETTINGS.styleFirst;
  }

  function splitPicks(picks){
    var keys = styleFirstKeys(), style = [], rest = [];
    picks.forEach(function(p){
      if(keys.indexOf(p.cat.key) > -1) style.push(p); else rest.push(p);
    });
    return { style: style, rest: rest };
  }

  function moduleLines(picks, plain){
    return picks.map(function(p){
      return say("moduleLine", { LABEL: p.cat.label.toUpperCase(), label: p.cat.label,
                                 v: fill(plain ? p.it.t : textOf(p.it)) });
    }).join("\n");
  }

  function castBlock(){
    var cast = activeCast().filter(function(p){ return (p.name||"").trim() || (p.desc||"").trim(); });
    if(!cast.length) return "";
    var withPhoto = cast.filter(function(p){ return !!p.photo; });
    var without = cast.filter(function(p){ return !p.photo && (p.name||"").trim(); });
    var lines = [say("castHeading")];
    lines.push(say(withPhoto.length ? "castWithPhotos" : "castWithoutPhotos"));
    var photos = photoBlock();
    if(photos) lines.push(photos);
    cast.forEach(function(p){
      var d = (p.desc||"").trim() || composeDescription(p);
      if(d){ lines.push(""); lines.push(d); }
    });
    var outfitKeys = castFieldList().filter(function(f){ return f.outfitRule; });
    var anyClothes = cast.some(function(p){
      return p.kind !== "animal" && outfitKeys.some(function(f){ return (p[f.key]||"").trim(); });
    });
    if(anyClothes){
      lines.push("");
      lines.push(say("outfitRule"));
    }
    if(without.length){
      var many = without.length > 1;
      var key = requirePhoto()
        ? (many ? "missingPhotoMany" : "missingPhotoOne")
        : (many ? "noPhotoMany" : "noPhotoOne");
      lines.push("");
      lines.push(say(key,
        { names: listNames(without.map(function(p){ return p.name.trim(); })) }));
    }
    return lines.join("\n");
  }

  function castSizeBlock(){
    var n = castSize();
    if(!n) return say("castSizeNone");
    var key = state.castOpen ? "castSizeOpen" : (n === 1 ? "castSizeOne" : "castSizeExact");
    var line = say(key);
    var strangers = say(state.strangers ? "strangersAllowed" : "strangersNone");
    return strangers ? line + "\n" + strangers : line;
  }

  function photoBlock(){
    var cast = activeCast().filter(function(p){ return (p.name||"").trim() && p.photo; });
    if(!cast.length) return "";
    var names = listNames(cast.map(function(p){ return p.name.trim(); }));
    var shots = 0;
    cast.forEach(function(p){ shots += (p.photos && p.photos.length) ? p.photos.length : 1; });
    var key;
    if(shots === 1) key = "photosOne";
    else if(cast.length === 1) key = "photosSomeOfOne";   /* several views of one person */
    else key = "photosMany";
    var line = say(key, { count: shots, names: names });
    var complete = say("photosComplete");
    return complete ? line + " " + complete : line;
  }

  function disciplineBlock(){
    if(!state.discipline || !MODEL.discipline.length) return "";
    var lines = [say("disciplineHeading")];
    MODEL.discipline.forEach(function(d){
      if(d.text) lines.push(fill(d.text));
    });
    return lines.join("\n");
  }

  function negativeRuleIds(){
    var out = [];
    MODEL.discipline.forEach(function(d){
      if(d.text && NEGATIVE_PHRASING.test(d.text)) out.push(d.id);
    });
    return out;
  }

  function assemble(){
    var mid = currentMasterId(), master = null;
    for(var i=0;i<MODEL.masters.length;i++){ if(MODEL.masters[i].id === mid) master = MODEL.masters[i]; }
    if(!master) return "No master prompt available. Load a pack containing one.";
    var picks = selected(), lines = [];
  
    if(state.followup){
      lines.push(askBlock());
      lines.push("");
      lines.push(say("followUpOpen"));
      lines.push("");
      var item = function(v){ lines.push(say("followUpItem", { v: v })); };
      picks.forEach(function(p){ item(fill(textOf(p.it))); });
      MODEL.dials.forEach(function(d){
        if(d.carryToFollowUp) item(dialText(d, state.dials[d.id]));
      });
      MODEL.fields.forEach(function(f){
        if(f.carryToFollowUp){ var v = fieldValue(f); if(v) item(v); }
      });
      lines.push("");
      lines.push(say("followUpClose"));
      var fd = disciplineBlock();
      if(fd){ lines.push(""); lines.push(fd); }
      return lines.join("\n");
    }
  
    lines.push(askBlock());
    lines.push("");
    lines.push(fill(masterBody(master)));
  
    var sizeLine = castSizeBlock();
    if(sizeLine){ lines.push(""); lines.push(fill(sizeLine)); }
  
    var ctxField = null;
    MODEL.fields.forEach(function(f){ if(f.section === "CONTEXT") ctxField = f; });
    if(ctxField){
      var ctx = fieldValue(ctxField);
      if(ctx){ lines.push(""); lines.push("CONTEXT"); lines.push(ctx); }
    }
  
    var split = splitPicks(picks);
    if(split.style.length){
      lines.push(""); lines.push(say("styleHeading"));
      lines.push(moduleLines(split.style));
      lines.push(""); lines.push(say("styleRule"));
    }
    lines.push(""); lines.push(mediumHoldLine());
  
    /* The standing rules, the craft block among them, belong with the style and
       ahead of the people for the same reason: they are how the picture is made,
       and a rule read after a reference photograph arrives is a rule applied to
       everything except the face. */
    MODEL.shared.forEach(function(s){
      (s.blocks || []).forEach(function(b){ lines.push(""); lines.push(fill(b)); });
      MODEL.fields.forEach(function(f){
        if(f.attachTo !== s.id) return;
        var v = fieldValue(f);
        if(v) lines.push(v);
      });
    });
  
    var cb = castBlock();
    if(cb){ lines.push(""); lines.push(cb); }
  
    if(split.rest.length){
      lines.push(""); lines.push(say("thisImageHeading"));
      lines.push(moduleLines(split.rest));
    }
  
    if(MODEL.dials.length){
      lines.push(""); lines.push(say("dialsHeading"));
      MODEL.dials.forEach(function(d){
        var t = dialText(d, state.dials[d.id]);
        if(t) lines.push(t);
      });
    }
  
    var vary = pickVariation();
    if(vary.length){ lines.push(""); lines.push(say("variationHeading")); lines.push(vary.join(" ")); }
  
    var sections = {}, order = [];
    MODEL.fields.forEach(function(f){
      if(f.attachTo || f.section === "CONTEXT") return;
      var v = fieldValue(f);
      if(!v) return;
      var sec = f.section || say("defaultSection");
      if(!sections[sec]){ sections[sec] = []; order.push(sec); }
      sections[sec].push(v);
    });
    order.forEach(function(sec){
      lines.push(""); lines.push(sec); lines.push(sections[sec].join("\n"));
    });
  
    var disc = disciplineBlock();
    if(disc){ lines.push(""); lines.push(disc); }
  
    return lines.join("\n");
  }

  function assemblePublic(){
    var mid = currentMasterId();
    /* Module numbers are assigned per model, so a selection cannot be carried
       across by number once private packs are dropped. Carry it by wording. */
    var wanted = {};
    selected().forEach(function(p){ wanted[p.it.t] = true; });
  
    var keepModel = MODEL, keepOn = state.on;
    MODEL = modelFrom(publicPacks());
    state.on = {};
    MODEL.categories.forEach(function(c){
      c.items.forEach(function(it){ if(wanted[it.t]) state.on[it.n] = true; });
    });
    publicMode = true;
    try{
      var master = null, i;
      for(i=0;i<MODEL.masters.length;i++){ if(MODEL.masters[i].id === mid) master = MODEL.masters[i]; }
      if(!master){
        return "This master prompt comes from a pack marked private, so there is nothing here to share. "
             + "Choose a master from a pack that is not private, or publish that pack.";
      }
      var picks = selected(), lines = [];
      if(asksQuestions()){
        lines.push(say("publicIntro"));
        lines.push("");
        lines.push(say("publicWhenToAsk"));
      } else {
        lines.push(say("askHeading"));
        lines.push(say("askOff"));
      }
      var split = splitPicks(picks);
      if(split.style.length){
        lines.push(""); lines.push(say("styleHeading"));
        lines.push(moduleLines(split.style, true));
        lines.push(""); lines.push(say("styleRule"));
      }
      lines.push(""); lines.push(mediumHoldLine());
      /* Standing rules before anybody is described, for the same reason the
         style goes first: read afterwards, they arrive as a comment on a face
         that has already been settled. */
      MODEL.shared.forEach(function(sh){
        (sh.blocks || []).forEach(function(b){ lines.push(""); lines.push(fill(b)); });
      });
      lines.push("");
      lines.push(say("publicCharacters"));
      if(state.castOpen){
        lines.push("");
        lines.push(say("publicCharactersOpen"));
        lines.push("");
        lines.push(say("publicAskHowMany"));
      }
      lines.push("");
      lines.push(fill(castSizeBlock()));
      lines.push("");
      lines.push(say("publicContext"));
      lines.push("");
      lines.push(fill(masterBody(master)));
      lines.push("");
      lines.push(publicCastBlock());
      if(split.rest.length){
        lines.push(""); lines.push(say("thisImageHeading"));
        lines.push(moduleLines(split.rest, true));
      }
      if(MODEL.dials.length){
        lines.push(""); lines.push(say("dialsHeading"));
        MODEL.dials.forEach(function(d){
          var txt = dialText(d, state.dials[d.id]);
          if(txt) lines.push(txt);
        });
      }
      var vary = pickVariation();
      if(vary.length){ lines.push(""); lines.push(say("variationHeading")); lines.push(vary.join(" ")); }
      var disc = disciplineBlock();
      if(disc){ lines.push(""); lines.push(disc); }
      return lines.join("\n");
    } finally {
      MODEL = keepModel; state.on = keepOn; publicMode = false;
    }
  }

  function publicCastBlock(){
    var fields = castFieldList();
    /* Zero is a real choice the counter offers, so an empty cast stays empty
       here. With no blocks there is nothing to replace, so the form is just the
       heading and the invitation to add the first character. */
    var n = Math.max(0, Math.min(MAX_CAST, parseInt(state.castCount, 10) || 0));
    var lines = [say("castHeading")];
    if(n) lines.push(say("publicCastIntro"));
    for(var i = 0; i < n; i++){
      var id = "Person_" + (i + 1);
      var animal = !!(state.cast[i] && state.cast[i].kind === "animal");
      lines.push("");
      lines.push(say(animal ? "publicCastWhoAnimal" : "publicCastWhoPerson", { id: id }));
      lines.push(say("publicCastName", { id: id }));
      fields.forEach(function(f){
        if(animal && f.outfitRule) return;
        lines.push(say("publicCastField", { label: f.label || f.key, hint: f.hint || f.label || f.key }));
      });
    }
    lines.push("");
    lines.push(state.castOpen
      ? say("publicCastRepeat", { next: "Person_" + (n + 1) })
      : say("publicCastComplete"));
    return lines.join("\n");
  }

  function esc(s){
    return String(s === undefined || s === null ? "" : s)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  /* ---------------- the interface an agent uses ---------------- */

  function rebuild(){
    buildModel();
    ensureDials();
    ensureCast();
    return MODEL;
  }

  function setPacks(packs){
    loadedPacks = (packs || []).slice();
    rebuild();
    return api;
  }

  function setState(patch){
    patch = patch || {};
    for(var k in patch) state[k] = patch[k];
    if(patch.seed !== undefined) seed = patch.seed;
    ensureCast();
    return api;
  }

  function getState(){ return JSON.parse(JSON.stringify(state)); }

  /* What this build offers, so an agent can read it rather than probe for it. */
  function capabilities(){
    rebuildIfNeeded();
    return {
      bench: PROFILE.bench,
      name: PROFILE.name || PROFILE.bench,
      engine: "1",
      maxCast: MODEL.settings.maxCast,
      masters: MODEL.masters.map(function(m){
        return { id: m.id, name: m.name, blurb: m.blurb || "",
                 castSizes: Object.keys(m.alt || {}).map(Number).sort() };
      }),
      categories: MODEL.categories.map(function(c){
        return { key: c.key, label: c.label, note: c.note || "", modules: c.items.length };
      }),
      dials: MODEL.dials.map(function(d){
        return { id: d.id, label: d.label, min: d.min === undefined ? 0 : d.min,
                 max: d.max === undefined ? 10 : d.max,
                 value: d.value, lo: d.lo || "", hi: d.hi || "" };
      }),
      fields: MODEL.fields.map(function(f){
        return { id: f.id, label: f.label, hint: f.hint || "", section: f.section || "" };
      }),
      modes: ["prompt", "followup", "shareable"],
      switches: ["discipline", "strangers", "castOpen", "askQuestions"],
      askCount: { min: MODEL.settings.minQuestions, max: MODEL.settings.maxQuestions },
      mediumHold: { min: 0, max: 10, meaning: "0 the reference photograph decides how a face is drawn, 10 the medium does" },
      modules: MODEL.count
    };
  }

  /* The whole vocabulary, with every module's requirements stated, so an agent
     can tell in advance what will work for the image being asked for. */
  function model(){
    rebuildIfNeeded();
    return {
      bench: PROFILE.bench,
      masters: MODEL.masters,
      categories: MODEL.categories.map(function(c){
        return { key: c.key, label: c.label, note: c.note || "", order: c.order,
                 items: c.items.map(function(it){
                   return { n: it.n, m: it.m, t: it.t, needs: needsOf(it),
                            alt: it.alt || null, strangers: it.strangers === true };
                 }) };
      }),
      dials: MODEL.dials, fields: MODEL.fields, variation: MODEL.variation,
      castFields: MODEL.castFields, wording: MODEL.wording, settings: MODEL.settings,
      discipline: MODEL.discipline, count: MODEL.count
    };
  }

  /* Which modules are usable right now, and which are not, with the reason. */
  function offered(){
    rebuildIfNeeded();
    var mid = currentMasterId(), on = [], off = [];
    MODEL.categories.forEach(function(c){
      c.items.forEach(function(it){
        var row = { n: it.n, category: c.key, text: fill(textOf(it)), needs: needsOf(it) };
        if(!suitsMaster(it, mid)) return;               /* another master's module */
        if(fitsCast(it)) on.push(row);
        else {
          row.reason = (it.strangers === true && !state.strangers)
            ? "brings people from outside the cast"
            : "needs " + needsOf(it) + " characters";
          off.push(row);
        }
      });
    });
    return { master: mid, usable: on, held: off };
  }

  function build(mode){
    rebuildIfNeeded();
    if(mode === "shareable") return assemblePublic();
    var wasFollowUp = state.followup;
    if(mode === "followup") state.followup = true;
    if(mode === "prompt" || mode === undefined) state.followup = false;
    var text = assemble();
    state.followup = wasFollowUp;
    return text;
  }

  /* A recipe is what an agent writes down and a person can load: it addresses
     modules by their wording, because numbers move when packs change. */
  function toRecipe(name){
    rebuildIfNeeded();
    var mods = [];
    selected().forEach(function(p){ mods.push(p.it.t); });
    return {
      recipe: 1, bench: PROFILE.bench, name: name || "",
      master: currentMasterId(), modules: mods,
      dials: JSON.parse(JSON.stringify(state.dials)),
      fields: JSON.parse(JSON.stringify(state.fields)),
      castCount: castSize(),
      cast: activeCast().map(function(p){
        var out = { name: p.name || "", kind: p.kind || "person" };
        MODEL.castFields.forEach(function(f){ if(p[f.key]) out[f.key] = p[f.key]; });
        return out;
      }),
      discipline: !!state.discipline, strangers: !!state.strangers,
      castOpen: !!state.castOpen, askQuestions: asksQuestions(), askCount: askCount(),
      mediumHold: mediumHold(), seed: seed
    };
  }

  function fromRecipe(recipe){
    recipe = recipe || {};
    rebuildIfNeeded();
    var want = {};
    (recipe.modules || []).forEach(function(t){ want[t] = true; });
    state.on = {};
    MODEL.categories.forEach(function(c){
      c.items.forEach(function(it){ if(want[it.t]) state.on[it.n] = true; });
    });
    if(recipe.master) state.master = recipe.master;
    if(recipe.dials) for(var d in recipe.dials) state.dials[d] = recipe.dials[d];
    if(recipe.fields) for(var f in recipe.fields) state.fields[f] = recipe.fields[f];
    if(recipe.castCount !== undefined) state.castCount = recipe.castCount;
    if(recipe.cast){
      /* A recipe describes its cast completely, so the slots are rebuilt from
         it rather than merged onto whatever the packs happened to seed. Merging
         would leave somebody else's clothing on your character. */
      state.cast = [];
      ensureCast();
      recipe.cast.forEach(function(person, i){
        if(i >= MAX_CAST) return;
        var slot = blankPerson();
        for(var k in person) slot[k] = person[k];
        state.cast[i] = slot;
      });
    }
    state.discipline = !!recipe.discipline;
    state.strangers = !!recipe.strangers;
    state.castOpen = !!recipe.castOpen;
    /* Absent means asking, the same as a fresh page and a setup saved before
       the control existed. Only an explicit false turns it off. */
    state.askQuestions = (recipe.askQuestions === undefined) ? true : !!recipe.askQuestions;
    if(recipe.askCount !== undefined) state.askCount = recipe.askCount;
    if(recipe.mediumHold !== undefined) state.mediumHold = recipe.mediumHold;
    if(recipe.seed !== undefined) seed = recipe.seed;
    ensureCast();
    /* Three different things can go wrong with a recipe's modules, and an
       agent can only act on the difference: the pack is missing, or the module
       belongs to another master, or the cast is too small for it and it has no
       wording for this size. Say which. */
    var asked = (recipe.modules || []).length, got = selected().length;
    var installed = {}, mid = currentMasterId();
    MODEL.categories.forEach(function(c){
      c.items.forEach(function(it){ installed[it.t] = it; });
    });
    var notInstalled = [], wrongMaster = [], tooFewCharacters = [];
    (recipe.modules || []).forEach(function(t){
      var it = installed[t];
      if(!it){ notInstalled.push(t); return; }
      if(!suitsMaster(it, mid)){ wrongMaster.push(t); return; }
      if(!fitsCast(it)) tooFewCharacters.push(t);
    });
    return { applied: got, asked: asked, missing: asked - got,
             notInstalled: notInstalled, wrongMaster: wrongMaster,
             tooFewCharacters: tooFewCharacters, master: mid };
  }

  function rebuildIfNeeded(){ if(!MODEL) rebuild(); }

  var api = {
    setPacks: setPacks, setState: setState, getState: getState,
    capabilities: capabilities, model: model, offered: offered,
    assemble: build, toRecipe: toRecipe, fromRecipe: fromRecipe,
    rebuild: rebuild
  };
  rebuild();
  return api;
}

if(typeof module !== "undefined" && module.exports) module.exports = { createBench: createBench };
