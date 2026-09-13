"use strict";

/* Optional runtime extensions used by DLC dials.
   Static dials behave exactly as before. */
(function(){
  if(typeof MODEL === "undefined" || typeof state === "undefined") return;

  var originalBlankPerson = blankPerson;
  blankPerson = function(){
    var p = originalBlankPerson();
    if(p.species === undefined) p.species = "";
    return p;
  };
  (state.cast || []).forEach(function(p){ if(p.species === undefined) p.species = ""; });

  function animalSpecies(p){
    if(!p || p.kind !== "animal") return "person";
    var explicit = String(p.species || "").trim().toLowerCase();
    if(explicit) return explicit;
    var hay = [p.name, p.looks, p.marker, p.desc].join(" ").toLowerCase();
    var known = [
      "parrot","cockatoo","budgie","macaw","canary","finch","sparrow","pigeon","crow","raven","eagle","hawk","falcon","owl","chicken","duck","goose","turkey","penguin","swan","bird",
      "snake","lizard","gecko","iguana","crocodile","alligator","turtle","tortoise","dragon","shark","salmon","trout","goldfish","koi","carp","fish",
      "cow","dog","cat","horse","goat","sheep","rabbit","mouse","rat","hamster","guinea pig","pig","bear","fox","wolf","lion","tiger","leopard","cheetah","monkey","ape","gorilla","chimpanzee","giraffe","deer","moose","otter","ferret","donkey","zebra","camel","alpaca","llama","bat",
      "frog","toad","salamander","newt"
    ];
    for(var i=0;i<known.length;i++){
      var re = new RegExp("\\b" + known[i].replace(/[-/\\^$*+?.()|[\]{}]/g,"\\$&") + "\\b");
      if(re.test(hay)) return known[i];
    }
    return "animal";
  }

  function coveringFor(p){
    if(!p || p.kind !== "animal") return "hair";
    var species = animalSpecies(p);
    var birds = ["parrot","cockatoo","budgie","macaw","canary","finch","sparrow","pigeon","crow","raven","eagle","hawk","falcon","owl","chicken","duck","goose","turkey","penguin","swan","bird"];
    var scales = ["snake","lizard","gecko","iguana","crocodile","alligator","turtle","tortoise","dragon","shark","salmon","trout","goldfish","koi","carp","fish"];
    var hair = ["cow","dog","cat","horse","goat","sheep","rabbit","mouse","rat","hamster","guinea pig","pig","bear","fox","wolf","lion","tiger","leopard","cheetah","monkey","ape","gorilla","chimpanzee","giraffe","deer","moose","otter","ferret","donkey","zebra","camel","alpaca","llama","bat"];
    var skin = ["frog","toad","salamander","newt"];
    if(birds.indexOf(species) > -1) return "feathers";
    if(scales.indexOf(species) > -1) return "scales";
    if(hair.indexOf(species) > -1) return "hair";
    if(skin.indexOf(species) > -1) return "skin";
    return (species && species !== "animal") ? species + " covering" : "animal covering";
  }

  function dialLocalFill(text, ctx){
    ctx = ctx || {};
    return fill(String(text).replace(/\{(name|species|covering|selected|selection|slot)\}/g, function(whole, key){
      return ctx[key] === undefined ? whole : ctx[key];
    }));
  }

  function selectedCategoryItems(key){
    var mid = currentMasterId(), out = [];
    MODEL.categories.forEach(function(c){
      if(c.key !== key) return;
      c.items.forEach(function(it){ if(state.on[it.n] && suits(it, mid)) out.push(it); });
    });
    return out;
  }

  function selectionLabel(text){
    var clean = String(text || "").replace(/\s+/g," ").trim();
    var first = clean.split(/[.;:]/)[0].trim() || clean;
    return first.length > 58 ? first.slice(0,55).replace(/\s+\S*$/,"" ) + "…" : first;
  }

  function dialInstances(){
    var out = [];
    MODEL.dials.forEach(function(d){
      var minSelected = (d.minSelected === undefined ? 1 : d.minSelected);
      if(d.whenCategory && selectedCategoryItems(d.whenCategory).length < minSelected) return;

      if(d.repeatFor === "cast"){
        activeCast().forEach(function(p, i){
          var name = (p.name || "").trim() || "Character " + (i+1);
          out.push({def:d, id:d.id+"::cast:"+(i+1), ctx:{
            name:name, species:animalSpecies(p), covering:coveringFor(p), slot:String(i+1)
          }});
        });
        return;
      }

      if(d.repeatFor === "selected"){
        var items = selectedCategoryItems(d.category || "");
        if(items.length < minSelected) return;
        items.forEach(function(it){
          out.push({def:d, id:d.id+"::selected:"+it.n, ctx:{
            selected:fill(it.t), selection:selectionLabel(fill(it.t)), slot:String(it.n)
          }});
        });
        return;
      }

      out.push({def:d, id:d.id, ctx:{}});
    });
    return out;
  }

  window.promptBenchDynamicDials = {
    instances:dialInstances,
    coveringFor:coveringFor,
    animalSpecies:animalSpecies
  };

  dialText = function(inst, v){
    var d = inst.def || inst, stops = d.stops || [], ctx = inst.ctx || {};
    for(var i=0;i<stops.length;i++){
      if(v <= stops[i].upTo) return dialLocalFill(String(stops[i].text).replace(/\{v\}/g, v), ctx);
    }
    return stops.length ? dialLocalFill(String(stops[stops.length-1].text).replace(/\{v\}/g, v), ctx) : "";
  };

  var baseRenderPeople = renderPeople;
  renderPeople = function(){
    baseRenderPeople();
    var cards = el("people").querySelectorAll(".person");
    cards.forEach(function(card){
      var i = parseInt(card.dataset.i,10), p = state.cast[i];
      if(!p || p.kind !== "animal" || card.querySelector('[data-k="species"]')) return;
      var who = card.querySelector(".who");
      if(!who) return;
      var input = document.createElement("input");
      input.type = "text";
      input.dataset.k = "species";
      input.placeholder = "Animal type, e.g. cat, parrot";
      input.value = p.species || "";
      input.setAttribute("aria-label", "Animal type");
      who.appendChild(input);
    });
  };

  renderDials = function(){
    var h = "", instances = dialInstances();
    instances.forEach(function(inst){
      var d = inst.def, min = (d.min === undefined ? 0 : d.min), max = (d.max === undefined ? 10 : d.max);
      if(state.dials[inst.id] === undefined) state.dials[inst.id] = (d.value === undefined ? min : d.value);
      h += '<div class="dial"><div class="row"><label for="d_'+esc(inst.id)+'">'+esc(dialLocalFill(d.label, inst.ctx))+'</label>'
        + '<output id="o_'+esc(inst.id)+'"></output></div>'
        + '<input type="range" id="d_'+esc(inst.id)+'" min="'+min+'" max="'+max+'" step="1" value="'+state.dials[inst.id]+'">'
        + '<div class="ends"><span>'+esc(dialLocalFill(d.lo===undefined?min:d.lo, inst.ctx))+'</span><span>'+esc(dialLocalFill(d.hi===undefined?max:d.hi, inst.ctx))+'</span></div></div>';
    });
    el("dials").innerHTML = h;
    instances.forEach(function(inst){
      var d = inst.def, input = el("d_"+inst.id);
      if(!input) return;
      var show = function(){
        var v = parseInt(input.value,10);
        if(isNaN(v)) v = (d.value === undefined ? (d.min === undefined ? 0 : d.min) : d.value);
        state.dials[inst.id] = v;
        el("o_"+inst.id).textContent = dialText(inst, v);
      };
      input.addEventListener("input", function(){ show(); saveState(); });
      show();
    });
  };

  assemble = function(){
    var mid = currentMasterId(), master = null;
    for(var i=0;i<MODEL.masters.length;i++){ if(MODEL.masters[i].id === mid) master = MODEL.masters[i]; }
    if(!master) return "No master prompt available. Load a pack containing one.";
    var picks = selected(), lines = [];

    if(el("followup").checked){
      lines.push("Keep the previous image exactly as it is: same characters, same style, same palette, same composition. Change only the following.");
      lines.push("");
      picks.forEach(function(p){ lines.push("- " + fill(p.it.t)); });
      dialInstances().forEach(function(inst){
        if(inst.def.carryToFollowUp){ var dt = dialText(inst, state.dials[inst.id]); if(dt) lines.push("- " + dt); }
      });
      MODEL.fields.forEach(function(f){
        if(f.carryToFollowUp){ var v = fieldValue(f); if(v) lines.push("- " + v); }
      });
      lines.push("");
      lines.push("Do not redraw anything else. Do not change anyone's face, clothing or position unless listed above.");
      return lines.join("\n");
    }

    lines.push(fill(master.body));
    var ctxField = null;
    MODEL.fields.forEach(function(f){ if(f.section === "CONTEXT") ctxField = f; });
    if(ctxField){ var ctx = fieldValue(ctxField); if(ctx){ lines.push(""); lines.push("CONTEXT"); lines.push(ctx); } }

    var cb = castBlock();
    if(cb){ lines.push(""); lines.push(cb); }

    MODEL.shared.forEach(function(s){
      (s.blocks || []).forEach(function(b){ lines.push(""); lines.push(fill(b)); });
      MODEL.fields.forEach(function(f){
        if(f.attachTo !== s.id) return;
        var v = fieldValue(f); if(v) lines.push(v);
      });
    });

    if(picks.length){
      lines.push(""); lines.push("THIS IMAGE");
      var block = [];
      picks.forEach(function(p){ block.push(p.cat.label.toUpperCase() + ": " + fill(p.it.t)); });
      lines.push(block.join("\n"));
    }

    var dialList = dialInstances();
    if(dialList.length){
      lines.push(""); lines.push("DIALS");
      dialList.forEach(function(inst){ var t = dialText(inst, state.dials[inst.id]); if(t) lines.push(t); });
    }

    var vary = pickVariation();
    if(vary.length){ lines.push(""); lines.push("VARIATION"); lines.push(vary.join(" ")); }

    var sections = {}, order = [];
    MODEL.fields.forEach(function(f){
      if(f.attachTo || f.section === "CONTEXT") return;
      var v = fieldValue(f); if(!v) return;
      var sec = f.section || "ALSO";
      if(!sections[sec]){ sections[sec] = []; order.push(sec); }
      sections[sec].push(v);
    });
    order.forEach(function(sec){ lines.push(""); lines.push(sec); lines.push(sections[sec].join("\n")); });
    return lines.join("\n");
  };

  el("people").addEventListener("input", function(e){
    if(e.target && (e.target.dataset.k === "name" || e.target.dataset.k === "species")) renderDials();
  });
  el("people").addEventListener("change", function(e){
    if(e.target && e.target.dataset.k === "kind"){ renderPeople(); renderDials(); }
  });
  document.addEventListener("change", function(e){
    var t = e.target;
    if((t && t.name === "master") || (t && t.type === "checkbox" && t.dataset && t.dataset.n)) renderDials();
  });
  el("counter").addEventListener("click", function(e){
    if(e.target.closest("button[data-count]")) renderDials();
  });

  renderPeople();
  renderDials();
})();
