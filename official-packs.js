"use strict";

/* Official Prompt Bench DLC importer.
   This UI can only talk to the same-origin /api/official-packs endpoint.
   Repository, branch and GitHub credentials live exclusively on the server. */
(function(){
  if(typeof el !== "function" || typeof savePacks !== "function" || typeof rebuild !== "function") return;
  if(el("officialPacks")) return;

  var loadFolder = el("loadFolder");
  if(!loadFolder || !loadFolder.parentNode) return;
  var bar = loadFolder.parentNode;
  var officialCatalogue = [];

  var style = document.createElement("style");
  style.textContent =
    ".officialpanel{background:var(--paper-2);border:1px solid var(--rule);padding:10px 12px;margin:0 0 10px}" +
    ".officialpanel[hidden]{display:none}.officialrow{display:flex;gap:8px;align-items:stretch}" +
    ".officialrow select{flex:1;min-width:0;background:#fff;border:1px solid var(--ink);color:var(--ink);font:500 14px/1.3 inherit;padding:9px}" +
    ".officialrow button{flex:0 0 auto;padding:10px 12px;font-size:14px}.officialpanel .hint{margin:8px 0 0}";
  document.head.appendChild(style);

  var button = document.createElement("button");
  button.type = "button";
  button.id = "officialPacks";
  button.textContent = "Official DLC";
  bar.insertBefore(button, bar.firstChild);

  var panel = document.createElement("div");
  panel.id = "officialPanel";
  panel.className = "officialpanel";
  panel.hidden = true;
  panel.innerHTML =
    '<div class="officialrow">' +
      '<select id="officialSelect" aria-label="Official DLC pack"><option>Loading official packs…</option></select>' +
      '<button id="installOfficial" type="button" disabled>Install</button>' +
    '</div>' +
    '<p class="hint" id="officialInfo">Only packs published in the official Prompt Bench pack repository can be imported here.</p>';
  bar.parentNode.insertBefore(panel, bar.nextSibling);

  var hint = bar.previousElementSibling;
  if(hint && hint.classList && hint.classList.contains("hint")){
    hint.textContent = "Install official DLC from the Prompt Bench repository, or load your own JSON files. Installed packs are kept on this device. Official import is restricted to the supported Prompt Bench pack repository.";
  }

  function installedOfficial(id){
    return loadedPacks.some(function(p){ return p.source === "official" && p.officialPack === id; });
  }

  function showOfficialInfo(){
    var sel = el("officialSelect"), info = el("officialInfo"), install = el("installOfficial");
    if(!sel || !info || !officialCatalogue.length) return;
    var id = sel.value, found = null;
    officialCatalogue.forEach(function(p){ if(p.id === id) found = p; });
    if(!found) return;
    var installed = installedOfficial(found.id);
    info.textContent = (found.description || "Official Prompt Bench DLC.")
      + (found.version ? " Version " + found.version + "." : "")
      + " " + found.fileCount + " file" + (found.fileCount === 1 ? "" : "s") + "."
      + (installed ? " Installed on this device; use Update to replace it with the current official version." : "");
    install.textContent = installed ? "Update" : "Install";
  }

  function loadOfficialCatalogue(){
    if(location.protocol === "file:" || typeof fetch !== "function"){
      note("Official DLC import is available in the served Chrome build, not when the HTML file is opened directly.");
      return;
    }
    var sel = el("officialSelect"), install = el("installOfficial");
    panel.hidden = false;
    sel.innerHTML = '<option>Loading official packs…</option>';
    install.disabled = true;
    fetch("api/official-packs", {cache:"no-store"}).then(function(r){
      return r.json().catch(function(){ return {}; }).then(function(body){
        if(!r.ok || !body.ok) throw new Error(body.error || "Official DLC catalogue could not be loaded.");
        return body;
      });
    }).then(function(body){
      officialCatalogue = Array.isArray(body.packs) ? body.packs : [];
      if(!officialCatalogue.length) throw new Error("The official DLC catalogue is empty.");
      var h = "";
      officialCatalogue.forEach(function(p){
        h += '<option value="' + esc(p.id) + '">' + esc(p.name) + (p.version ? " · " + esc(p.version) : "") + '</option>';
      });
      sel.innerHTML = h;
      install.disabled = false;
      showOfficialInfo();
      note(officialCatalogue.length + " official DLC pack" + (officialCatalogue.length === 1 ? "" : "s") + " available.");
    }).catch(function(err){
      officialCatalogue = [];
      sel.innerHTML = '<option>Official DLC unavailable</option>';
      el("officialInfo").textContent = err.message || "Official DLC catalogue could not be loaded.";
      note(el("officialInfo").textContent);
    });
  }

  function installOfficialPack(){
    var sel = el("officialSelect"), install = el("installOfficial"), id = sel.value;
    if(!id || !officialCatalogue.length) return;
    install.disabled = true;
    install.textContent = installedOfficial(id) ? "Updating…" : "Installing…";
    fetch("api/official-packs?id=" + encodeURIComponent(id), {cache:"no-store"}).then(function(r){
      return r.json().catch(function(){ return {}; }).then(function(body){
        if(!r.ok || !body.ok) throw new Error(body.error || "Official DLC could not be imported.");
        return body;
      });
    }).then(function(body){
      if(!Array.isArray(body.files) || !body.files.length) throw new Error("That official DLC contains no pack files.");
      var incoming = [];
      body.files.forEach(function(f){
        if(!f || !f.path || !f.data || typeof f.data !== "object" || Array.isArray(f.data)){
          throw new Error("Official DLC returned a malformed pack file.");
        }
        incoming.push({
          name: f.data.pack || f.path.replace(/^.*\//, "").replace(/\.json$/i, ""),
          path: "official:" + f.path,
          source: "official",
          officialPack: body.id,
          officialVersion: body.version || "",
          data: f.data
        });
      });
      loadedPacks = loadedPacks.filter(function(p){
        return !(p.source === "official" && p.officialPack === body.id);
      }).concat(incoming);
      savePacks();
      rebuild();
      showOfficialInfo();
      note(body.name + " installed from the official Prompt Bench repository (" + body.files.length + " file" + (body.files.length === 1 ? "" : "s") + ").");
    }).catch(function(err){
      note(err.message || "Official DLC could not be imported.");
      showOfficialInfo();
    }).then(function(){
      install.disabled = false;
      showOfficialInfo();
    });
  }

  button.addEventListener("click", function(){
    if(!panel.hidden && officialCatalogue.length){
      panel.hidden = true;
      return;
    }
    loadOfficialCatalogue();
  });
  el("officialSelect").addEventListener("change", showOfficialInfo);
  el("installOfficial").addEventListener("click", installOfficialPack);
})();
