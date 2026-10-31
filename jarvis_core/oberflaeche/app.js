/* JARVIS - Oberfläche.
 * Sie zeigt nur, was der Server wirklich weiß: keine erfundenen Zahlen, keine simulierten Agenten.
 * Alle Texte kommen per textContent ins Dokument (nie als HTML), die Seite braucht keine fremden Adressen. */
(function () {
  "use strict";

  /* ============================================================ Helfer === */
  var NS = "http://www.w3.org/2000/svg";
  function $(sel, wurzel) { return (wurzel || document).querySelector(sel); }
  function $$(sel, wurzel) { return Array.prototype.slice.call((wurzel || document).querySelectorAll(sel)); }

  function anhaengen(e, kinder) {
    kinder.forEach(function (k) {
      if (Array.isArray(k)) { anhaengen(e, k); return; }
      if (k === null || k === undefined || k === false) return;
      e.appendChild(k.nodeType ? k : document.createTextNode(String(k)));
    });
  }
  function h(tag, attr) {
    var e = document.createElement(tag);
    var a = attr || {};
    Object.keys(a).forEach(function (k) {
      var v = a[k];
      if (v === undefined || v === null || v === false) return;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else if (k.indexOf("on") === 0) e.addEventListener(k.slice(2), v);
      else if (v === true) e.setAttribute(k, "");
      else e.setAttribute(k, v);
    });
    anhaengen(e, Array.prototype.slice.call(arguments, 2));
    return e;
  }
  function sv(tag, attr) {
    var e = document.createElementNS(NS, tag);
    var a = attr || {};
    Object.keys(a).forEach(function (k) { e.setAttribute(k, a[k]); });
    anhaengen(e, Array.prototype.slice.call(arguments, 2));
    return e;
  }
  function leeren(e) { while (e.firstChild) e.removeChild(e.firstChild); return e; }

  function lesen(k) { try { return window.localStorage.getItem(k); } catch (e) { return null; } }
  function schreiben(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* ohne Speicher merkt sich der Browser nichts - die Seite läuft trotzdem */ } }

  var fZeit = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  var fUhr = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" });
  var fSek = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  var fTag = new Intl.DateTimeFormat("de-DE", { weekday: "short", day: "2-digit", month: "short" });
  var fZahl = new Intl.NumberFormat("de-DE");
  function parse(utc) { var d = new Date(utc); return isNaN(d.getTime()) ? null : d; }
  function datum(utc) { var d = parse(utc); return d ? fZeit.format(d) : ""; }
  function uhr(utc) { var d = parse(utc); return d ? fUhr.format(d) : ""; }
  function vor(utc) {
    var d = parse(utc);
    if (!d) return "";
    var s = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
    if (s < 60) return "gerade eben";
    if (s < 3600) return "vor " + Math.round(s / 60) + " Min.";
    if (s < 86400) return "vor " + Math.round(s / 3600) + " Std.";
    return "vor " + Math.round(s / 86400) + " Tagen";
  }
  function dauer(ms) {
    if (ms === null || ms === undefined) return "";
    return ms < 1000 ? ms + " ms" : (ms / 1000).toFixed(1).replace(".", ",") + " s";
  }
  function kuerzen(text, n) { text = String(text === null || text === undefined ? "" : text); return text.length > n ? text.slice(0, n - 1) + "…" : text; }
  function eingabeZeit(wert) { return wert ? String(wert).replace("T", " ") : ""; }

  var BEREICH_NAMEN = { geschaeft: "Geschäft", privat: "Privat", allgemein: "Allgemein", technik: "Technik" };
  function bereichName(b) { return BEREICH_NAMEN[b] || (b ? b.charAt(0).toUpperCase() + b.slice(1) : ""); }
  var ART_NAMEN = { regel: "Regeln", profil: "Profil", ziel: "Ziele", strategie: "Strategie", projekt: "Projekte", entscheidung: "Entscheidungen",
    praeferenz: "Vorlieben", fakt: "Fakten", technik: "Technik" };
  var ART_EINZEL = { regel: "Regel", profil: "Profil", ziel: "Ziel", strategie: "Strategie", projekt: "Projekt", entscheidung: "Entscheidung",
    praeferenz: "Vorliebe", fakt: "Fakt", technik: "Technik" };
  var ART_REIHE = ["regel", "profil", "ziel", "strategie", "projekt", "entscheidung", "praeferenz", "fakt", "technik"];
  var AUFTRAG_NAMEN = { entwurf: "Entwurf", rueckfrage: "Rückfrage", geplant: "Geplant", wartend: "Wartet", laeuft: "Läuft",
    wartet_auf_freigabe: "Wartet auf Freigabe", pausiert: "Pausiert", unterbrochen: "Unterbrochen", fertig: "Fertig",
    fehlgeschlagen: "Fehlgeschlagen", abgebrochen: "Abgebrochen" };
  var SCHRITT_NAMEN = { offen: "offen", laeuft: "läuft", fertig: "fertig", fehlgeschlagen: "fehlgeschlagen", blockiert: "blockiert" };
  var AKTION_NAMEN = { ausgefuehrt: "ausgeführt", fehler: "Fehler", freigabe_offen: "wartet auf Freigabe", gesperrt: "gesperrt", ungueltig: "ungültig" };
  var WERKZEUG_NAMEN = { datei_schreiben: "Datei schreiben", datei_loeschen: "Datei löschen", datei_lesen: "Datei lesen",
    dateien_auflisten: "Dateien auflisten", aufgabe_anlegen: "Aufgabe anlegen", aufgabe_status: "Aufgabe ändern",
    erinnerung_setzen: "Erinnerung setzen", merken: "Merken", recherche: "Internet-Recherche", umgebung_pruefen: "Mac-Umgebung prüfen",
    auftrag_planen: "Auftrag planen" };
  var ICONS = {
    jarvis: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
    leitstand: "M4 20V11 M10 20V4 M16 20v-6 M21 20H3",
    auftraege: "M9 6h11 M9 12h11 M9 18h11 M4.5 6h.01 M4.5 12h.01 M4.5 18h.01",
    wissen: "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z M5 17a3 3 0 0 1 3-3h11",
    system: "M4 7h9 M17 7h3 M4 17h3 M11 17h9 M15 4v6 M9 14v6",
    mikro: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z M5 11a7 7 0 0 0 14 0 M12 18v3"
  };
  function icon(name) { return sv("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }, sv("path", { d: ICONS[name] })); }
  function badge(text, klasse) { return h("span", { class: "badge " + (klasse || ""), text: text }); }

  /* ============================================================ Zustand === */
  var S = {
    daten: null, bereich: lesen("jv_bereich"), gespraech: null, alle: false,
    ansicht: lesen("jv_ansicht") || "jarvis", wartet: false, ausstehend: null,
    offline: false, cache: {}, ladeNr: 0, angewandt: 0,
    offeneSchritte: {}, antworten: {}, bearbeiteFakt: null, planLaeuft: false
  };
  function neu(schluessel, wert) {
    var j = JSON.stringify(wert);
    if (S.cache[schluessel] === j) return false;
    S.cache[schluessel] = j;
    return true;
  }
  function tippt(wurzel) {
    var a = document.activeElement;
    if (!a || !wurzel || !wurzel.contains(a)) return false;
    if (a.tagName === "INPUT") return !/^(checkbox|radio|button|submit)$/.test(a.type); // Schalter und Knöpfe sperren das Neuzeichnen nicht
    return a.tagName === "TEXTAREA" || a.tagName === "SELECT";
  }
  function laufendeAuftraege() {
    var z = S.daten && S.daten.zaehler.auftraege || {};
    return (z.laeuft || 0) + (z.wartend || 0) + (z.wartet_auf_freigabe || 0);
  }

  var toastTimer = null;
  function meldung(text, fehler) {
    var t = $("#toast");
    t.textContent = text;
    t.className = "sichtbar" + (fehler ? " fehler" : "");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () { t.className = ""; }, fehler ? 7000 : 3500);
  }

  /* ================================================================= API === */
  function api(methode, pfad, daten) {
    var optionen = { method: methode, credentials: "same-origin", cache: "no-store", headers: {} };
    if (daten !== undefined) { optionen.headers["Content-Type"] = "application/json"; optionen.body = JSON.stringify(daten); }
    return window.fetch(pfad, optionen).then(function (a) {
      return a.json().then(function (inhalt) { return { code: a.status, daten: inhalt }; },
        function () { return { code: a.status, daten: { ok: false, fehler: "Unerwartete Antwort (HTTP " + a.status + ")." } }; });
    }, function () {
      return { code: 0, daten: { ok: false, fehler: "Keine Verbindung zu JARVIS. Läuft der Server? (./jarvis.sh start)" } };
    });
  }
  /* Aktion mit Rückmeldung: gibt true zurück, wenn der Server "ok" sagte. */
  async function tun(methode, pfad, daten, erfolgText) {
    var r = await api(methode, pfad, daten);
    if (r.code === 401) { $("#zugang-fehlt").hidden = false; return false; }
    if (r.code >= 200 && r.code < 300 && r.daten.ok !== false) {
      if (erfolgText) meldung(erfolgText === true ? (r.daten.meldung || "Erledigt.") : erfolgText);
      S.cache = {};
      await laden();
      return r;
    }
    meldung(r.daten.fehler || r.daten.meldung || "Das hat nicht geklappt (HTTP " + r.code + ").", true);
    return false;
  }

  async function laden() {
    var q = [];
    if (S.bereich) q.push("bereich=" + encodeURIComponent(S.bereich));
    if (S.gespraech) q.push("gespraech=" + encodeURIComponent(S.gespraech));
    if (S.alle) q.push("alle=1");
    var nr = ++S.ladeNr;
    var r = await api("GET", "/api/zustand" + (q.length ? "?" + q.join("&") : ""));
    if (nr < S.angewandt) return false; // eine neuere Antwort wurde schon angezeigt
    S.angewandt = nr;
    if (r.code === 401) { $("#zugang-fehlt").hidden = false; S.offline = true; zeichnenKopf(); kernSetzen(); return false; }
    $("#zugang-fehlt").hidden = true;
    if (r.code !== 200) { S.offline = true; zeichnenKopf(); kernSetzen(); return false; }
    S.offline = false;
    S.daten = r.daten;
    S.bereich = r.daten.bereich;
    S.gespraech = r.daten.gespraech;
    schreiben("jv_bereich", S.bereich);
    zeichnen();
    return true;
  }
  var pollTimer = null;
  function pollenPlanen() {
    window.clearTimeout(pollTimer);
    var d = S.daten;
    var schnell = S.wartet || (d && (d.system.beschaeftigt || d.system.stimme.spricht || laufendeAuftraege() > 0));
    pollTimer = window.setTimeout(function () { laden().then(pollenPlanen, pollenPlanen); }, document.hidden ? 8000 : (schnell ? 1000 : 3000));
  }

  /* ========================================================= Reiter, Kopf === */
  var ANSICHTEN = [["jarvis", "Jarvis"], ["leitstand", "Leitstand"], ["auftraege", "Aufträge"], ["wissen", "Wissen"], ["system", "System"]];
  function reiterBauen() {
    var nav = leeren($("#reiter"));
    ANSICHTEN.forEach(function (a) {
      nav.appendChild(h("button", { type: "button", role: "tab", id: "reiter-" + a[0], "aria-selected": "false", "aria-controls": "ansicht-" + a[0],
        onclick: function () { ansichtWechseln(a[0]); } }, icon(a[0]), h("span", { text: a[1] }), h("span", { class: "zeichen", hidden: true })));
    });
  }
  function ansichtWechseln(id) {
    if (!ANSICHTEN.some(function (a) { return a[0] === id; })) id = "jarvis";
    S.ansicht = id;
    schreiben("jv_ansicht", id);
    $$(".ansicht").forEach(function (e) { e.classList.toggle("aktiv", e.id === "ansicht-" + id); });
    $$("#reiter button").forEach(function (b) { b.setAttribute("aria-selected", b.id === "reiter-" + id ? "true" : "false"); });
    S.cache = {};
    zeichnen();
    if (id === "system") systemProtokolleLaden();
    window.scrollTo(0, 0);
  }
  function reiterZeichen(id, n) {
    var z = $("#reiter-" + id + " .zeichen");
    if (!z) return;
    z.hidden = !n;
    z.textContent = n ? String(n) : "";
  }

  function zeichnenKopf() {
    var d = S.daten;
    var gesperrt = !!(d && d.system.gesperrt);
    $("#sperre").hidden = !gesperrt;
    var bereich = d ? d.bereich : (S.bereich || "geschaeft");
    document.body.setAttribute("data-bereich", bereich);
    $("#privat-hinweis").hidden = bereich !== "privat";
    var schluessel = [d && d.system.bereiche, bereich];
    if (neu("kopf-bereiche", schluessel)) {
      var wahl = leeren($("#bereichswahl"));
      ((d && d.system.bereiche) || [bereich]).forEach(function (b) {
        wahl.appendChild(h("button", { type: "button", "aria-pressed": b === bereich ? "true" : "false", text: bereichName(b),
          onclick: function () { bereichWechseln(b); } }));
      });
    }
    var chips = [];
    if (S.offline) {
      chips.push(h("span", { class: "chip" }, h("span", { class: "punkt fehler" }), "Keine Verbindung"));
    } else if (d) {
      var p = d.system.provider.claude_code || {};
      chips.push(h("span", { class: "chip", title: p.hinweis || "" }, h("span", { class: "punkt " + (p.nutzbar ? "ok" : "fehler") }),
        "Claude Code ", h("b", { text: p.nutzbar ? "bereit" : "nicht bereit" })));
      chips.push(h("span", { class: "chip", title: "Modell für Gespräche (unter System änderbar)" }, "Modell ", h("b", { text: d.system.modelle.chat || "Standard" })));
      if (d.system.lan) chips.push(h("span", { class: "chip", title: "Erreichbar aus dem WLAN" }, h("span", { class: "punkt warn" }), "WLAN offen"));
    }
    var minute = Math.floor(Date.now() / 60000);
    if (neu("kopf-chips", [S.offline, d && d.system.provider, d && d.system.modelle.chat, d && d.system.lan, minute])) {
      var box = leeren($("#chips"));
      chips.forEach(function (c) { box.appendChild(c); });
      box.appendChild(h("span", { class: "chip chip-datum" }, fTag.format(new Date()) + " " + fUhr.format(new Date())));
    }
    var offen = d ? d.freigaben.length : 0;
    document.title = (offen ? "(" + offen + ") " : "") + "JARVIS";
  }
  function bereichWechseln(b) {
    if (b === S.bereich) return;
    S.bereich = b;
    S.gespraech = null;
    S.cache = {};
    laden();
  }

  function zeichnenReiterZeichen() {
    var d = S.daten;
    reiterZeichen("jarvis", d.freigaben.length);
    reiterZeichen("auftraege", laufendeAuftraege());
  }

  /* ================================================================= Kern === */
  var kern = null;
  function kernZustand() {
    var d = S.daten;
    if (S.offline || !d) return "offline";
    if (d.system.gesperrt) return "gesperrt";
    if (d.system.stimme.spricht) return "spricht";
    if (S.wartet || d.system.beschaeftigt) return "denkt";
    if (Sprache.laeuft) return "hoert";
    return "bereit";
  }
  var KERN_NAMEN = { bereit: "bereit", hoert: "hört zu", denkt: "denkt …", spricht: "spricht", gesperrt: "notstopp", offline: "keine verbindung" };
  function kernSetzen() {
    var z = kernZustand();
    if (kern) kern.zustand(z);
    var d = S.daten, detail = "";
    if (z === "gesperrt") detail = "Notstopp ist aktiv";
    else if (z === "offline") detail = S.offline && !d ? "Server nicht erreichbar" : "Verbindung unterbrochen";
    else if (z === "spricht") detail = "Stimme: " + (d.system.stimme.stimme || "Systemstimme");
    else if (z === "denkt") detail = "Modell " + (d.system.modelle.chat || "Standard");
    else if (z === "hoert") detail = Sprache.wartetBis > Date.now() ? "Ich höre dir zu …" : (Sprache.modus === "dauer" ? "Sag „Hey Jarvis“ …" : "Sprich jetzt …");
    else if (d.freigaben.length) detail = d.freigaben.length + " Freigabe(n) warten auf dich";
    else if (laufendeAuftraege()) detail = laufendeAuftraege() + " Auftrag/Aufträge in Arbeit";
    $("#kern-zustand").textContent = KERN_NAMEN[z];
    $("#kern-detail").textContent = detail;
  }

  /* =============================================================== Chat === */
  function nachrichtBauen(n) {
    var meta = n.meta || {};
    var teile = [h("div", { class: "blase", text: n.text })];
    if (meta.aktionen && meta.aktionen.length) {
      teile.push(h("div", { class: "aktionen" }, meta.aktionen.map(function (a) {
        return h("span", { class: "aktion-chip", title: a.text || "" }, kuerzen(a.kurz || a.werkzeug, 70),
          h("span", { class: "badge b-" + a.status, text: AKTION_NAMEN[a.status] || a.status }));
      })));
    }
    var info = [];
    if (n.zeit) info.push(h("span", { text: uhr(n.zeit) }));
    if (n.rolle === "jarvis" && meta.modell) info.push(h("span", { text: meta.modell }));
    if (n.rolle === "jarvis" && meta.dauer_ms) info.push(h("span", { text: dauer(meta.dauer_ms) }));
    if (meta.ausgewichen) info.push(h("span", { class: "warn", text: "Hinweis: " + meta.ausgewichen }));
    if (info.length) teile.push(h("div", { class: "meta" }, info));
    return h("div", { class: "nachricht " + n.rolle }, teile);
  }
  function zeichnenChat() {
    var d = S.daten, box = $("#chat");
    var denkt = S.wartet || d.system.beschaeftigt;
    if (!neu("chat", [d.gespraech, d.nachrichten.map(function (n) { return n.id; }), S.ausstehend, denkt])) return;
    var amEnde = box.scrollHeight - box.scrollTop - box.clientHeight < 90;
    leeren(box);
    if (!d.nachrichten.length && !S.ausstehend) {
      box.appendChild(h("div", { class: "chat-leer" }, h("p", { text: "Noch keine Nachrichten in diesem Bereich." }),
        h("p", { class: "klein", text: "Frag zum Beispiel: „Was steht heute an?“ oder „Wie prüfe ich, ob eine Firma echt ist?“" })));
      return;
    }
    d.nachrichten.forEach(function (n) { box.appendChild(nachrichtBauen(n)); });
    if (S.ausstehend) box.appendChild(nachrichtBauen({ rolle: "nutzer", text: S.ausstehend, zeit: null }));
    if (denkt) box.appendChild(h("div", { class: "nachricht jarvis denkt" }, h("div", { class: "blase" }, h("i"), h("i"), h("i"))));
    if (amEnde || S.ausstehend) box.scrollTop = box.scrollHeight;
  }

  async function senden(text) {
    text = (text || "").trim();
    if (!text) return;
    if (S.wartet) { meldung("JARVIS antwortet noch. Bitte gleich nochmal.", true); return; }
    if (S.daten && S.daten.system.gesperrt) { meldung("Notstopp ist aktiv. Erst entsperren.", true); return; }
    var vorherId = S.daten && S.daten.nachrichten.length ? S.daten.nachrichten[S.daten.nachrichten.length - 1].id : 0;
    S.wartet = true;
    S.ausstehend = text;
    $("#senden").disabled = true;
    $("#abbrechen").hidden = false;
    zeichnenChat();
    kernSetzen();
    var r = await api("POST", "/api/anfrage", { text: text, gespraech: S.gespraech || undefined, bereich: S.bereich || undefined });
    S.wartet = false;
    S.ausstehend = null;
    $("#senden").disabled = false;
    $("#abbrechen").hidden = true;
    if (r.code === 0) { await nachAbbruchNachsehen(text, vorherId); pollenPlanen(); return; }
    if (r.daten.gespraech) S.gespraech = r.daten.gespraech;
    if (!r.daten.ok) {
      if (!r.daten.gespraech && !$("#text").value) $("#text").value = text; // wurde nicht gespeichert: nichts geht verloren
      meldung(r.daten.fehler || "Keine Antwort.", true);
    }
    S.cache = {};
    await laden();
    if (r.daten.ok) {
      var st = S.daten && S.daten.system.stimme;
      if (st && st.vorlesen && st.verfuegbar) sprechen(r.daten.antwort);
      if (r.daten.freigaben && r.daten.freigaben.length) meldung("Eine Freigabe wartet auf dich. Ohne dein Ja passiert nichts.");
    }
    pollenPlanen();
  }
  /* Bricht der Browser eine lange Anfrage ab (manche Browser tun das nach etwa einer Minute), arbeitet der Server trotzdem weiter.
     Dann wird nachgesehen, ob JARVIS noch arbeitet, statt einen falschen Fehler zu melden. */
  async function nachAbbruchNachsehen(text, vorherId) {
    meldung("Die Verbindung wurde unterbrochen. Ich schaue nach, ob JARVIS noch antwortet …");
    var ende = Date.now() + 6 * 60000, gesehen = false;
    while (Date.now() < ende) {
      await new Promise(function (r) { window.setTimeout(r, 2000); });
      var ok = await laden();
      if (!ok) { if (gesehen) break; continue; }
      if (S.daten.system.beschaeftigt) { gesehen = true; continue; }
      break;
    }
    S.cache = {};
    await laden();
    var letzte = S.daten && S.daten.nachrichten[S.daten.nachrichten.length - 1];
    if (!(letzte && letzte.rolle === "jarvis" && letzte.id > vorherId)) {
      $("#text").value = $("#text").value || text;
      meldung("Es kam keine Antwort. Dein Text steht wieder im Eingabefeld.", true);
    }
  }
  async function sprechen(text) {
    var r = await api("POST", "/api/sprich", { text: text });
    if (r.code === 200) laden().then(pollenPlanen);
  }
  function eingabeBauen() {
    var feld = $("#text");
    function wachsen() { feld.style.height = "auto"; feld.style.height = Math.min(feld.scrollHeight, 160) + "px"; }
    feld.addEventListener("input", wachsen);
    feld.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#eingabe").requestSubmit(); }
    });
    $("#eingabe").addEventListener("submit", function (e) {
      e.preventDefault();
      var t = feld.value;
      if (!t.trim()) return;
      if (S.wartet) { meldung("JARVIS antwortet noch. Einen Moment – dein Text bleibt stehen."); return; }
      feld.value = "";
      wachsen();
      senden(t);
    });
    $("#abbrechen").addEventListener("click", function () { api("POST", "/api/abbrechen", {}).then(function () { meldung("Abbruch angefordert."); }); });
  }

  /* ========================================================== Freigaben === */
  function freigabeKarte(f, minuten) {
    var ende = parse(f.zeit);
    var rest = ende ? Math.round((ende.getTime() + minuten * 60000 - Date.now()) / 60000) : 0;
    var knoepfe = [];
    var ja = h("button", { type: "button", class: "knopf knopf-primaer", text: "Ja, ausführen", onclick: function () { entscheiden(f.id, "ja", knoepfe); } });
    var nein = h("button", { type: "button", class: "knopf", text: "Nein, ablehnen", onclick: function () { entscheiden(f.id, "nein", knoepfe); } });
    knoepfe.push(ja, nein);
    return h("section", { class: "karte freigabe" },
      h("div", { class: "freigabe-kopf" },
        h("strong", { text: "Freigabe #" + f.id + ": " + (WERKZEUG_NAMEN[f.werkzeug] || f.werkzeug) }),
        badge(bereichName(f.bereich), f.bereich === "privat" ? "privat" : ""),
        f.auftrag_id ? badge("Auftrag #" + f.auftrag_id) : null,
        h("span", { class: "klein", text: rest > 0 ? "gültig noch " + rest + " Min." : "läuft gleich ab" })),
      f.risiko ? h("p", { class: "risiko", text: f.risiko }) : null,
      h("pre", { class: "vorschau", text: f.vorschau }),
      h("div", { class: "knopfreihe" }, ja, nein));
  }
  async function entscheiden(id, wert, knoepfe) {
    knoepfe.forEach(function (k) { k.disabled = true; });
    var r = await api("POST", "/api/freigabe", { id: id, entscheidung: wert });
    if (r.code === 200) {
      if (wert === "nein") meldung("Abgelehnt. Es wurde nichts ausgeführt.");
      else if (r.daten.ok) meldung("Ausgeführt.");
      else meldung("Ausgeführt, aber mit Fehler: " + kuerzen(r.daten.ergebnis && r.daten.ergebnis.text, 200), true);
    } else {
      meldung(r.daten.fehler || "Das hat nicht geklappt.", true);
    }
    S.cache = {};
    await laden();
    if (r.code === 200 && r.daten.weiter) senden("Weiter – die Freigabe wurde erteilt, das Ergebnis steht oben im Gespräch.");
  }
  function zeichnenFreigaben(container, schluessel, leerText) {
    var d = S.daten;
    var minute = Math.floor(Date.now() / 60000);
    if (!neu(schluessel, [d.freigaben.map(function (f) { return f.id; }), minute])) return;
    leeren(container);
    if (!d.freigaben.length) {
      if (leerText) container.appendChild(h("p", { class: "leer", text: leerText }));
      return;
    }
    d.freigaben.forEach(function (f) { container.appendChild(freigabeKarte(f, d.system.freigabe_minuten)); });
  }

  /* ========================================================= Jarvis-Seite === */
  function zahl(wert, beschriftung, klasse) { return h("div", { class: "zahl " + (klasse || "") }, h("b", { text: String(wert) }), h("span", { text: beschriftung })); }
  function zeichnenMini() {
    var d = S.daten, v = d.system.verbrauch;
    var teile = [v.anfragen, d.freigaben.length, laufendeAuftraege(), d.zaehler.fakten];
    if (!neu("mini", teile)) return;
    var box = leeren($("#mini"));
    box.appendChild(zahl(v.anfragen, "Anfragen heute"));
    box.appendChild(zahl(d.freigaben.length, "Freigaben offen", d.freigaben.length ? "warn" : ""));
    box.appendChild(zahl(laufendeAuftraege(), "Aufträge aktiv"));
    box.appendChild(zahl(d.zaehler.fakten, "Gedächtnis"));
  }

  /* ============================================================ Diagramme === */
  function balkenDiagramm(stunden) {
    var B = 240, H = 70, platz = B / stunden.length;
    var max = Math.max.apply(null, stunden.map(function (s) { return s.anzahl; }).concat([1]));
    var svg = sv("svg", { class: "diagramm balken", viewBox: "0 0 " + B + " " + (H + 2), role: "img", "aria-label": "Anfragen pro Stunde in den letzten 24 Stunden" });
    stunden.forEach(function (s, i) {
      var x = i * platz + 1.5, w = platz - 3, g = sv("g", {});
      var von = parse(s.von);
      var titel = (von ? von.getHours() + " Uhr" : "") + ": " + s.anzahl + (s.anzahl === 1 ? " Anfrage" : " Anfragen") + (s.fehler ? ", davon " + s.fehler + " mit Fehler" : "");
      if (!s.anzahl) {
        g.appendChild(sv("rect", { class: "n", x: x, y: H - 2, width: w, height: 2 }));
      } else {
        var gesamt = Math.max(4, (s.anzahl / max) * H), fehler = (s.fehler / s.anzahl) * gesamt;
        g.appendChild(sv("rect", { class: "b", x: x, y: H - gesamt, width: w, height: gesamt - fehler }));
        if (s.fehler) g.appendChild(sv("rect", { class: "f", x: x, y: H - fehler, width: w, height: fehler }));
      }
      g.appendChild(sv("title", {}, titel));
      svg.appendChild(g);
    });
    svg.appendChild(sv("line", { class: "achse", x1: 0, x2: B, y1: H + 0.5, y2: H + 0.5 }));
    return svg;
  }
  function liniendiagramm(werte) {
    var B = 240, H = 70, n = werte.length, max = Math.max.apply(null, werte) || 1;
    var punkte = werte.map(function (w, i) { return [n === 1 ? B / 2 : (i / (n - 1)) * B, H - 4 - (w / max) * (H - 10)]; });
    var d = "M" + punkte.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" L");
    var svg = sv("svg", { class: "diagramm", viewBox: "0 0 " + B + " " + H, role: "img", "aria-label": "Antwortzeiten der letzten Anfragen" });
    svg.appendChild(sv("line", { class: "achse", x1: 0, x2: B, y1: H - 0.5, y2: H - 0.5 }));
    if (n > 1) {
      svg.appendChild(sv("path", { class: "flaeche", d: d + " L" + B + "," + H + " L0," + H + " Z" }));
      svg.appendChild(sv("path", { class: "linie", d: d }));
    }
    var letzter = punkte[punkte.length - 1];
    svg.appendChild(sv("circle", { class: "punkt-ende", cx: letzter[0], cy: letzter[1], r: 3.2 }));
    return svg;
  }
  function donut(teile, gesamt) {
    var U = 2 * Math.PI * 50, versatz = 0;
    var svg = sv("svg", { class: "donut", viewBox: "0 0 128 128", role: "img", "aria-label": "Aufträge nach Zustand" });
    svg.appendChild(sv("circle", { class: "grund", cx: 64, cy: 64, r: 50 }));
    teile.forEach(function (t) {
      var laenge = (t.wert / gesamt) * U;
      svg.appendChild(sv("circle", { class: "seg seg-" + t.status, cx: 64, cy: 64, r: 50,
        "stroke-dasharray": laenge.toFixed(2) + " " + (U - laenge).toFixed(2), "stroke-dashoffset": (-versatz).toFixed(2) }));
      versatz += laenge;
    });
    svg.appendChild(sv("text", { x: 64, y: 58 }, String(gesamt)));
    svg.appendChild(sv("text", { class: "u", x: 64, y: 80 }, gesamt === 1 ? "Auftrag" : "Aufträge"));
    return svg;
  }
  function ring(anteil, text) {
    var U = 2 * Math.PI * 36;
    return sv("svg", { class: "ring", viewBox: "0 0 84 84", role: "img", "aria-label": "Erfolgsquote " + text },
      sv("circle", { class: "grund", cx: 42, cy: 42, r: 36 }),
      sv("circle", { class: "wert", cx: 42, cy: 42, r: 36, "stroke-dasharray": (anteil * U).toFixed(2) + " " + U.toFixed(2) }),
      sv("text", { x: 42, y: 42 }, text));
  }
  function stat(label, wert) { return h("div", { class: "agent lang" }, h("span", { class: "name", text: label }), h("span", { class: "info", text: wert })); }

  /* ============================================================ Leitstand === */
  function karte(id) { return leeren($("#" + id + " .inhalt")); }

  function zeichnenLeitstand() {
    var d = S.daten;
    if (neu("l-anfragen", d.diagramme.stunden)) {
      var k1 = karte("k-anfragen"), st = d.diagramme.stunden;
      var summe = st.reduce(function (a, s) { return a + s.anzahl; }, 0), fehler = st.reduce(function (a, s) { return a + s.fehler; }, 0);
      k1.appendChild(h("div", { class: "zahlen" }, zahl(summe, "in 24 Stunden"), zahl(fehler, "davon Fehler", fehler ? "fehler" : "")));
      if (summe) {
        k1.appendChild(h("div", { style: "margin-top:12px" }, balkenDiagramm(st)));
        k1.appendChild(h("div", { class: "beschriftung" }, h("span", { text: uhr(st[0].von) }), h("span", { text: "jetzt" })));
      } else {
        k1.appendChild(h("p", { class: "leer", text: "Noch keine Anfragen in den letzten 24 Stunden." }));
      }
    }
    if (neu("l-antwort", d.diagramme.antwortzeiten)) {
      var k2 = karte("k-antwort"), z = d.diagramme.antwortzeiten;
      if (!z.length) {
        k2.appendChild(h("p", { class: "leer", text: "Noch keine Antworten gemessen." }));
      } else {
        var mittel = z.reduce(function (a, b) { return a + b; }, 0) / z.length;
        k2.appendChild(h("div", { class: "zahlen" }, zahl(dauer(z[z.length - 1]), "letzte"), zahl(dauer(Math.round(mittel)), "Durchschnitt"), zahl(dauer(Math.max.apply(null, z)), "längste")));
        k2.appendChild(h("div", { style: "margin-top:12px" }, liniendiagramm(z)));
        k2.appendChild(h("div", { class: "beschriftung" }, h("span", { text: z.length + " Antworten" }), h("span", { text: "neueste rechts" })));
      }
    }
    if (neu("l-auftraege", d.zaehler.auftraege)) {
      var k3 = karte("k-auftraege"), za = d.zaehler.auftraege;
      var status = Object.keys(za).filter(function (s) { return za[s] > 0; });
      var gesamt = status.reduce(function (a, s) { return a + za[s]; }, 0);
      if (!gesamt) {
        k3.appendChild(h("p", { class: "leer", text: "Noch keine Aufträge. Unter „Aufträge“ planst du den ersten." }));
      } else {
        k3.appendChild(h("div", { class: "donut-zeile" }, donut(status.map(function (s) { return { status: s, wert: za[s] }; }), gesamt),
          h("div", { class: "legende" }, status.map(function (s) {
            return h("span", {}, h("i", { class: "badge b-" + s, style: "padding:0;width:10px;height:10px;background:currentColor;border:0" }), AUFTRAG_NAMEN[s] || s, h("b", { text: String(za[s]) }));
          }))));
      }
    }
    if (neu("l-heute", d.system.verbrauch)) {
      var k4 = karte("k-heute"), v = d.system.verbrauch;
      var quote = v.anfragen ? (v.anfragen - v.fehler) / v.anfragen : null;
      k4.appendChild(h("div", { class: "donut-zeile" },
        quote === null ? null : ring(quote, Math.round(quote * 100) + " %"),
        h("div", { class: "zahlen", style: "flex:1" }, zahl(v.anfragen, "Modellaufrufe"), zahl(v.fehler, "Fehler", v.fehler ? "fehler" : ""),
          zahl(fZahl.format(v.tokens_ein), "Token rein"), zahl(fZahl.format(v.tokens_aus), "Token raus"))));
      k4.appendChild(h("p", { class: "klein", style: "margin-top:10px", text: "Die Token-Zahlen meldet Claude Code. Ein festes Limit deines Abos kennt JARVIS nicht – bei Erreichen weicht er sichtbar auf Sonnet aus." }));
    }
    if (neu("l-wissen", [d.zaehler, d.system.letzte_sicherung])) {
      var k5 = karte("k-wissen"), zz = d.zaehler;
      k5.appendChild(h("div", { class: "zahlen" }, zahl(zz.fakten, "Einträge im Gedächtnis"), zahl(zz.vorschlaege, "Vorschläge offen", zz.vorschlaege ? "warn" : ""),
        zahl(zz.todos_offen, "Aufgaben offen"), zahl(zz.erinnerungen_faellig, "Erinnerungen fällig", zz.erinnerungen_faellig ? "warn" : "")));
      k5.appendChild(h("p", { class: "klein", style: "margin-top:10px", text: d.system.letzte_sicherung ? "Letzte Sicherung: " + datum(d.system.letzte_sicherung) + " (" + vor(d.system.letzte_sicherung) + ")" : "Noch keine Sicherung gemacht (läuft täglich automatisch)." }));
    }
    var s = d.status, p = d.system.provider.claude_code || {};
    if (neu("l-server", [s.laufzeit_sekunden > 60 ? Math.floor(s.laufzeit_sekunden / 60) : 0, s.anfragen, s.gesperrt, p, d.system.stimme.stimme, d.system.lan])) {
      var k6 = karte("k-server");
      k6.appendChild(stat("Claude Code", p.nutzbar ? (p.hinweis || "bereit") : "nicht bereit – " + (p.hinweis || "")));
      k6.appendChild(stat("Läuft seit", datum(s.seit) + " (" + vor(s.seit) + ")"));
      k6.appendChild(stat("Adresse", s.adresse + (s.lan ? " und im WLAN" : " (nur dieser Mac)")));
      k6.appendChild(stat("Version", "JARVIS " + s.version + " · Python " + s.python + " · Prozess " + s.pid));
      k6.appendChild(stat("Stimme", d.system.stimme.verfuegbar ? (d.system.stimme.stimme || "Systemstimme") : "nicht verfügbar (kein „say“)"));
      k6.appendChild(stat("Notstopp", s.gesperrt ? "AKTIV" : "aus"));
    }
    if (neu("l-agenten", [d.agenten, d.system.gesperrt, d.system.beschaeftigt])) {
      var k7 = karte("k-agenten"), ag = d.agenten;
      var orchZustand = d.system.gesperrt ? "gesperrt" : (d.system.beschaeftigt ? "arbeitet" : "bereit");
      k7.appendChild(h("div", { class: "agent" }, h("span", { class: "punkt " + (orchZustand === "arbeitet" ? "warn" : (orchZustand === "bereit" ? "ok" : "fehler")) }),
        h("span", { class: "name", text: "Orchestrator" }), h("span", { class: "info", text: "Modell " + ag.orchestrator.modell + " · " + orchZustand })));
      ag.rollen.forEach(function (r) {
        var aktiv = ag.aktiv.filter(function (x) { return x.rolle === r.id; })[0];
        var zuletzt = ag.zuletzt.filter(function (x) { return x.rolle === r.id; })[0];
        var info = aktiv ? "arbeitet: " + aktiv.titel + " (Auftrag #" + aktiv.auftrag_id + ")"
          : (zuletzt ? "zuletzt: " + zuletzt.titel + " – " + (SCHRITT_NAMEN[zuletzt.status] || zuletzt.status) + ", " + vor(zuletzt.beendet) : "bisher nicht gebraucht");
        k7.appendChild(h("div", { class: "agent" }, h("span", { class: "punkt " + (aktiv ? "warn" : "") }), h("span", { class: "name", text: r.name }),
          h("span", { class: "info", title: info, text: info })));
      });
      k7.appendChild(h("p", { class: "klein", style: "margin-top:8px", text: "Rollen sind keine erfundenen Mitarbeiter: Jeder Schritt eines Auftrags läuft als echter Modellaufruf mit genau einer Rolle und deren Werkzeugen." }));
    }
    zeichnenFreigaben($("#k-freigaben .inhalt"), "l-freigaben", "Keine offenen Freigaben. Alles, was etwas verändern würde, erscheint hier und läuft erst nach deinem Ja.");
    if (neu("l-log", d.log)) {
      var k8 = karte("k-log");
      if (!d.log.length) k8.appendChild(h("p", { class: "leer", text: "Noch keine Ereignisse." }));
      var log = h("div", { class: "log" });
      d.log.slice().reverse().forEach(function (e) {
        var rest = Object.keys(e).filter(function (k) { return ["zeit", "stufe", "ereignis"].indexOf(k) < 0; }).map(function (k) { return k + "=" + kuerzen(JSON.stringify(e[k]), 40); }).join(" ");
        log.appendChild(h("div", { class: e.stufe }, h("span", { class: "z", text: fSek.format(parse(e.zeit) || new Date()) }), h("span", { class: "e", text: e.ereignis }), h("span", { class: "d", text: rest })));
      });
      k8.appendChild(log);
    }
  }

  /* =============================================================== Aufträge === */
  function sicherKnopf(text, sicher, aktion) {
    var timer = null;
    var knopf = h("button", { type: "button", class: "knopf knopf-gefahr knopf-klein", text: text });
    knopf.addEventListener("click", function () {
      if (knopf.classList.contains("scharf")) { window.clearTimeout(timer); aktion(); return; }
      knopf.classList.add("scharf");
      knopf.textContent = sicher;
      timer = window.setTimeout(function () { knopf.classList.remove("scharf"); knopf.textContent = text; }, 3500);
    });
    return knopf;
  }
  function auftragsAktion(id, aktion, extra) {
    var daten = { aktion: aktion, id: id };
    Object.keys(extra || {}).forEach(function (k) { daten[k] = extra[k]; });
    return tun("POST", "/api/auftrag", daten, true);
  }
  function auftragsKnoepfe(a) {
    var st = a.status, reihe = [];
    function knopf(text, aktion, klasse) {
      return h("button", { type: "button", class: "knopf knopf-klein " + (klasse || ""), text: text, onclick: function () { auftragsAktion(a.id, aktion); } });
    }
    function loeschen() { return sicherKnopf("Löschen", "Wirklich löschen?", function () { auftragsAktion(a.id, "loeschen"); }); }
    if (st === "entwurf") {
      var zeitfeld = h("input", { type: "datetime-local", "aria-label": "Startzeit (leer = sofort)", style: "width:auto;min-height:30px;padding:3px 8px" });
      reihe.push(h("button", { type: "button", class: "knopf knopf-klein knopf-primaer", text: "Starten", onclick: function () {
        auftragsAktion(a.id, "starten", zeitfeld.value ? { start_um: eingabeZeit(zeitfeld.value) } : null);
      } }), zeitfeld, h("span", { class: "klein", text: "Zeit leer lassen = sofort" }), loeschen());
    } else if (st === "rueckfrage") {
      reihe.push(loeschen());
    } else if (st === "geplant" || st === "wartend" || st === "laeuft" || st === "wartet_auf_freigabe") {
      reihe.push(knopf("Pausieren", "pausieren"), knopf("Abbrechen", "abbrechen", "knopf-gefahr"));
    } else if (st === "pausiert" || st === "unterbrochen") {
      reihe.push(knopf("Fortsetzen", "fortsetzen", "knopf-primaer"), knopf("Abbrechen", "abbrechen", "knopf-gefahr"), loeschen());
    } else if (st === "fehlgeschlagen") {
      reihe.push(knopf("Nochmal versuchen", "wiederholen", "knopf-primaer"), loeschen());
    } else {
      reihe.push(loeschen());
    }
    return h("div", { class: "knopfreihe" }, reihe);
  }
  function schrittBauen(s) {
    var koerper = [];
    function abschnitt(titel, inhalt) { if (inhalt) koerper.push(h("div", {}, h("h3", { text: titel }), inhalt)); }
    abschnitt("Anweisung", h("p", { text: s.anweisung }));
    abschnitt("Erfolgskriterium", h("p", { text: s.kriterium }));
    if (s.datei) abschnitt("Erwartete Datei in der Werkstatt", h("p", { class: "mono", text: s.datei }));
    if (s.abhaengig_von && s.abhaengig_von.length) abschnitt("Wartet auf Schritt", h("p", { text: s.abhaengig_von.join(", ") }));
    if (s.ergebnis) abschnitt("Ergebnis", h("pre", { class: "vorschau", text: kuerzen(s.ergebnis, 4000) }));
    if (s.pruefung && s.pruefung.werkzeuge && s.pruefung.werkzeuge.length) {
      abschnitt("Tatsächlich ausgeführte Werkzeuge", h("div", { class: "aktionen" }, s.pruefung.werkzeuge.map(function (w) {
        return h("span", { class: "aktion-chip" }, kuerzen(w.kurz, 70), h("span", { class: "badge b-" + w.status, text: AKTION_NAMEN[w.status] || w.status }));
      })));
    }
    if (s.pruefung) abschnitt("Prüfschicht", h("p", { text: (s.pruefung.ok ? "Bestanden. " : "Nicht bestanden. ") + (s.pruefung.begruendung || "") }));
    var info = [];
    if (s.versuche) info.push(s.versuche + (s.versuche === 1 ? " Versuch" : " Versuche"));
    if (s.dauer_ms) info.push(dauer(s.dauer_ms));
    if (s.extern) info.push("enthielt Daten aus dem Internet (gilt als unvertrauenswürdig)");
    if (info.length) koerper.push(h("p", { class: "klein", text: info.join(" · ") }));
    var det = h("details", { class: "schritt" },
      h("summary", {}, h("span", { class: "nr", text: String(s.nr) }), h("span", { class: "rolle", text: (S.rollenNamen && S.rollenNamen[s.rolle]) || s.rolle }),
        h("span", { class: "titel", text: s.titel }), h("span", { class: "badge b-" + s.status, text: SCHRITT_NAMEN[s.status] || s.status })),
      h("div", { class: "koerper" }, koerper));
    if (S.offeneSchritte[s.id]) det.setAttribute("open", "");
    det.addEventListener("toggle", function () { S.offeneSchritte[s.id] = det.open; });
    return det;
  }
  function auftragKarte(a) {
    var d = S.daten;
    var teile = [h("div", { class: "auftrag-kopf" },
      h("strong", { text: "#" + a.id + "  " + a.titel }),
      h("span", { class: "badge b-" + a.status, text: AUFTRAG_NAMEN[a.status] || a.status }),
      badge(bereichName(a.bereich), a.bereich === "privat" ? "privat" : ""),
      h("span", { class: "klein", text: "Modellaufrufe " + a.aufrufe + " von " + d.system.max_aufrufe_pro_auftrag }))];
    if (a.ziel && a.ziel !== a.titel) teile.push(h("p", { class: "ziel", text: a.ziel }));
    if (a.status === "geplant" && a.geplant_fuer) teile.push(h("p", { class: "klein", text: "Startet am " + datum(a.geplant_fuer) }));
    if (a.gestartet) teile.push(h("p", { class: "klein", text: "Gestartet " + vor(a.gestartet) + (a.beendet ? ", beendet " + vor(a.beendet) : "") }));
    if (a.fehler) teile.push(h("p", { class: "fehlertext", text: a.fehler }));
    if (a.status === "rueckfrage" && a.rueckfragen) {
      var antwort = h("textarea", { rows: "3", placeholder: "Deine Antworten auf die Rückfragen …", "aria-label": "Antworten auf die Rückfragen" });
      antwort.value = S.antworten[a.id] || "";
      antwort.addEventListener("input", function () { S.antworten[a.id] = antwort.value; });
      teile.push(h("div", { class: "formular" },
        h("div", {}, a.rueckfragen.map(function (f, i) { return h("p", { text: (i + 1) + ". " + f }); })),
        antwort,
        h("div", { class: "knopfreihe" }, h("button", { type: "button", class: "knopf knopf-primaer knopf-klein", text: "Neu planen", onclick: function () {
          auftragsAktion(a.id, "neu_planen", { antworten: antwort.value });
        } }))));
    }
    (a.schritte || []).forEach(function (s) { teile.push(schrittBauen(s)); });
    if (a.ergebnis) teile.push(h("div", {}, h("h3", { class: "klein", text: "Ergebnis des Auftrags" }), h("pre", { class: "vorschau", text: kuerzen(a.ergebnis, 4000) })));
    teile.push(auftragsKnoepfe(a));
    return h("section", { class: "karte auftrag" }, teile);
  }
  function zeichnenAuftraege() {
    var d = S.daten, box = $("#auftraege-liste");
    S.rollenNamen = {};
    d.agenten.rollen.forEach(function (r) { S.rollenNamen[r.id] = r.name; });
    if (tippt(box)) return; // nicht stören, während jemand tippt
    if (!neu("auftraege", [d.auftraege, d.system.max_aufrufe_pro_auftrag, Math.floor(Date.now() / 60000)])) return;
    leeren(box);
    if (!d.auftraege.length) {
      box.appendChild(h("p", { class: "leer", text: "Noch keine Aufträge. Beschreibe oben, was erledigt werden soll – JARVIS macht daraus einen Plan zum Prüfen." }));
      return;
    }
    d.auftraege.forEach(function (a) { box.appendChild(auftragKarte(a)); });
  }
  function planFormBauen() {
    $("#plan-form").addEventListener("submit", async function (e) {
      e.preventDefault();
      var ziel = $("#plan-ziel").value.trim();
      if (!ziel || S.planLaeuft) return;
      var knopf = $("#plan-knopf"), ausgabe = $("#plan-ergebnis");
      S.planLaeuft = true;
      knopf.disabled = true;
      knopf.textContent = "JARVIS plant … (das kann eine Minute dauern)";
      var r = await api("POST", "/api/auftrag", { aktion: "planen", ziel: ziel, bereich: S.bereich || undefined });
      S.planLaeuft = false;
      knopf.disabled = false;
      knopf.textContent = "Plan erstellen";
      ausgabe.hidden = false;
      if (r.code === 200 && r.daten.ok) {
        $("#plan-ziel").value = "";
        ausgabe.textContent = r.daten.text;
        meldung(r.daten.status === "rueckfrage" ? "JARVIS hat Rückfragen." : "Entwurf erstellt. Prüfe ihn und starte ihn dann.");
      } else {
        ausgabe.textContent = r.daten.fehler || "Der Plan konnte nicht erstellt werden.";
        meldung(ausgabe.textContent, true);
      }
      S.cache = {};
      await laden();
    });
  }

  /* ================================================================ Wissen === */
  function zeichnenWissen() {
    var d = S.daten;
    var bereiche = d.system.bereiche.concat(["allgemein", "technik"]);
    if (neu("w-selects", [bereiche, d.bereich, S.alle])) {
      var filter = leeren($("#wissen-filter"));
      filter.appendChild(h("option", { value: "aktuell", text: "Nur " + bereichName(d.bereich) + " (plus Allgemein und Technik)" }));
      filter.appendChild(h("option", { value: "alle", text: "Alle Bereiche (nur Ansicht)" }));
      filter.value = S.alle ? "alle" : "aktuell";
      var fb = leeren($("#fakt-bereich"));
      bereiche.forEach(function (b) { fb.appendChild(h("option", { value: b, text: bereichName(b) })); });
      fb.value = d.bereich;
      var fa = leeren($("#fakt-art"));
      ART_REIHE.forEach(function (a) { fa.appendChild(h("option", { value: a, text: ART_EINZEL[a] || a })); });
      fa.value = "fakt";
    }
    zeichnenFakten();
    zeichnenTodos();
    zeichnenErinnerungen();
  }
  function fakt(f) {
    var inhalt = [h("div", {}, f.text),
      h("div", { class: "chips2" }, badge(bereichName(f.bereich), f.bereich === "privat" ? "privat" : ""),
        f.quelle === "nutzer" ? badge("von dir") : (f.quelle === "jarvis" ? badge("von JARVIS") : null))];
    var zeile = h("div", { class: "zeile" });
    var stern = h("button", { type: "button", class: "stern", "aria-pressed": f.wichtig ? "true" : "false", title: "Wichtig: immer im Blick", text: "★",
      onclick: function () { tun("POST", "/api/fakt", { aktion: "aendern", id: f.id, wichtig: !f.wichtig }); } });
    var leiste;
    if (f.status === "vorschlag") {
      leiste = h("div", { class: "aktionsleiste" },
        h("button", { type: "button", class: "knopf knopf-klein knopf-primaer", text: "Merken", onclick: function () { tun("POST", "/api/fakt", { aktion: "bestaetigen", id: f.id }, "Gemerkt."); } }),
        h("button", { type: "button", class: "knopf knopf-klein", text: "Verwerfen", onclick: function () { tun("POST", "/api/fakt", { aktion: "verwerfen", id: f.id }, "Verworfen."); } }));
    } else {
      leiste = h("div", { class: "aktionsleiste" },
        h("button", { type: "button", class: "knopf knopf-klein", text: "Bearbeiten", onclick: function () { S.bearbeiteFakt = f.id; S.cache = {}; zeichnenFakten(); } }),
        sicherKnopf("Löschen", "Sicher?", function () { tun("POST", "/api/fakt", { aktion: "loeschen", id: f.id }, "Gelöscht."); }));
    }
    anhaengen(zeile, [f.status === "vorschlag" ? null : stern, h("div", { class: "inhalt" }, inhalt), leiste]);
    return zeile;
  }
  function faktEditor(f, bereiche) {
    var text = h("textarea", { rows: "3", "aria-label": "Text" }); text.value = f.text;
    var bereich = h("select", { "aria-label": "Bereich" }, bereiche.map(function (b) { return h("option", { value: b, text: bereichName(b) }); })); bereich.value = f.bereich;
    var art = h("select", { "aria-label": "Art" }, ART_REIHE.map(function (a) { return h("option", { value: a, text: ART_EINZEL[a] || a }); })); art.value = f.art;
    return h("div", { class: "zeile" }, h("div", { class: "inhalt formular", style: "margin:0" }, text, h("div", { class: "formzeile" }, bereich, art),
      h("div", { class: "knopfreihe" },
        h("button", { type: "button", class: "knopf knopf-primaer knopf-klein", text: "Speichern", onclick: async function () {
          S.bearbeiteFakt = null;
          if (!(await tun("POST", "/api/fakt", { aktion: "aendern", id: f.id, text: text.value, bereich: bereich.value, art: art.value }, "Gespeichert."))) { S.cache = {}; zeichnenFakten(); }
        } }),
        h("button", { type: "button", class: "knopf knopf-klein", text: "Abbrechen", onclick: function () { S.bearbeiteFakt = null; S.cache = {}; zeichnenFakten(); } }))));
  }
  function zeichnenFakten() {
    var d = S.daten, box = $("#fakten-liste");
    if (S.bearbeiteFakt) { if (tippt(box)) return; }
    if (!neu("w-fakten", [d.fakten, S.bearbeiteFakt])) return;
    leeren(box);
    var bereiche = d.system.bereiche.concat(["allgemein", "technik"]);
    var vorschlaege = d.fakten.filter(function (f) { return f.status === "vorschlag"; });
    var fest = d.fakten.filter(function (f) { return f.status === "bestaetigt"; });
    if (vorschlaege.length) {
      box.appendChild(h("h3", { class: "klein", text: "JARVIS schlägt vor, das zu merken – nur mit deinem Ja" }));
      vorschlaege.forEach(function (f) { box.appendChild(fakt(f)); });
    }
    if (!fest.length) { box.appendChild(h("p", { class: "leer", text: "Noch nichts im Gedächtnis dieses Bereichs." })); return; }
    ART_REIHE.concat(Object.keys(ART_NAMEN).filter(function (a) { return ART_REIHE.indexOf(a) < 0; })).forEach(function (art) {
      var gruppe = fest.filter(function (f) { return f.art === art; });
      if (!gruppe.length) return;
      box.appendChild(h("h3", { class: "klein", style: "margin-top:6px", text: (ART_NAMEN[art] || art) + " (" + gruppe.length + ")" }));
      gruppe.forEach(function (f) { box.appendChild(f.id === S.bearbeiteFakt ? faktEditor(f, bereiche) : fakt(f)); });
    });
  }
  function zeichnenTodos() {
    var d = S.daten, box = $("#todo-liste");
    if (!neu("w-todos", d.todos)) return;
    leeren(box);
    if (!d.todos.length) { box.appendChild(h("p", { class: "leer", text: "Keine Aufgaben." })); return; }
    d.todos.forEach(function (t) {
      var erledigt = t.status === "erledigt";
      var ueberfaellig = !erledigt && t.faellig && parse(t.faellig) && parse(t.faellig).getTime() < Date.now();
      box.appendChild(h("div", { class: "zeile" + (erledigt ? " erledigt" : "") },
        h("input", { type: "checkbox", "aria-label": "Erledigt", checked: erledigt, style: "width:20px;height:20px;min-height:0;accent-color:#ff8a1f;margin-top:3px",
          onchange: function () { tun("POST", "/api/todo", { aktion: "status", id: t.id, status: erledigt ? "offen" : "erledigt" }); } }),
        h("div", { class: "inhalt" }, h("div", { text: t.titel }),
          h("div", { class: "chips2" }, t.prioritaet !== "normal" ? badge(t.prioritaet, t.prioritaet === "hoch" ? "warn" : "") : null,
            t.faellig ? badge("fällig " + datum(t.faellig), ueberfaellig ? "fehler" : "") : null, badge(bereichName(t.bereich), t.bereich === "privat" ? "privat" : ""))),
        h("div", { class: "aktionsleiste" }, sicherKnopf("Löschen", "Sicher?", function () { tun("POST", "/api/todo", { aktion: "loeschen", id: t.id }); }))));
    });
  }
  function zeichnenErinnerungen() {
    var d = S.daten, box = $("#erinnerung-liste");
    if (!neu("w-erinnerungen", d.erinnerungen)) return;
    leeren(box);
    if (!d.erinnerungen.length) { box.appendChild(h("p", { class: "leer", text: "Keine offenen Erinnerungen." })); return; }
    d.erinnerungen.forEach(function (e) {
      box.appendChild(h("div", { class: "zeile" },
        h("div", { class: "inhalt" }, h("div", { text: e.text }),
          h("div", { class: "chips2" }, badge(datum(e.faellig), e.status === "faellig" ? "warn" : ""), e.status === "faellig" ? badge("fällig", "warn") : null,
            badge(bereichName(e.bereich), e.bereich === "privat" ? "privat" : ""))),
        h("div", { class: "aktionsleiste" },
          h("button", { type: "button", class: "knopf knopf-klein", text: "Erledigt", onclick: function () { tun("POST", "/api/erinnerung", { aktion: "erledigt", id: e.id }); } }),
          sicherKnopf("Löschen", "Sicher?", function () { tun("POST", "/api/erinnerung", { aktion: "loeschen", id: e.id }); }))));
    });
  }
  function wissenFormenBauen() {
    $("#wissen-filter").addEventListener("change", function () { S.alle = this.value === "alle"; S.cache = {}; laden(); });
    $("#fakt-form").addEventListener("submit", async function (e) {
      e.preventDefault();
      var text = $("#fakt-text").value.trim();
      if (!text) return;
      var r = await tun("POST", "/api/fakt", { aktion: "hinzufuegen", text: text, bereich: $("#fakt-bereich").value, art: $("#fakt-art").value, wichtig: $("#fakt-wichtig").checked });
      if (r) { $("#fakt-text").value = ""; $("#fakt-wichtig").checked = false; if (r.daten.neu === false) meldung("Das steht schon im Gedächtnis."); else meldung("Gemerkt."); }
    });
    $("#todo-form").addEventListener("submit", async function (e) {
      e.preventDefault();
      var titel = $("#todo-titel").value.trim();
      if (!titel) return;
      var daten = { aktion: "anlegen", titel: titel, prioritaet: $("#todo-prio").value, bereich: S.bereich };
      if ($("#todo-faellig").value) daten.faellig = eingabeZeit($("#todo-faellig").value);
      if (await tun("POST", "/api/todo", daten, "Aufgabe angelegt.")) { $("#todo-titel").value = ""; $("#todo-faellig").value = ""; }
    });
    $("#erinnerung-form").addEventListener("submit", async function (e) {
      e.preventDefault();
      var text = $("#erinnerung-text").value.trim(), wann = $("#erinnerung-faellig").value;
      if (!text || !wann) return;
      if (await tun("POST", "/api/erinnerung", { aktion: "anlegen", text: text, faellig: eingabeZeit(wann), bereich: S.bereich }, "Erinnerung angelegt.")) {
        $("#erinnerung-text").value = ""; $("#erinnerung-faellig").value = "";
      }
    });
    var suchTimer = null;
    $("#suche").addEventListener("input", function () {
      window.clearTimeout(suchTimer);
      var q = this.value.trim(), box = $("#suche-treffer");
      if (!q) { box.hidden = true; leeren(box); return; }
      suchTimer = window.setTimeout(async function () {
        var r = await api("GET", "/api/suche?q=" + encodeURIComponent(q) + "&bereich=" + encodeURIComponent(S.bereich || ""));
        if ($("#suche").value.trim() !== q) return;
        box.hidden = false;
        leeren(box);
        box.appendChild(h("h3", { class: "klein", text: "Treffer für „" + q + "“" }));
        var treffer = (r.daten && r.daten.treffer) || [];
        if (!treffer.length) box.appendChild(h("p", { class: "leer", text: "Nichts gefunden." }));
        treffer.forEach(function (f) {
          box.appendChild(h("div", { class: "zeile" }, h("div", { class: "inhalt" }, h("div", { text: f.text }),
            h("div", { class: "chips2" }, badge(bereichName(f.bereich), f.bereich === "privat" ? "privat" : ""), badge(ART_NAMEN[f.art] || f.art)))));
        });
      }, 300);
    });
  }

  /* ================================================================ System === */
  function einstellungSpeichern(daten, text) { return tun("POST", "/api/einstellungen", daten, text || "Gespeichert."); }
  function modellAuswahl(wert) {
    var namen = ["opus", "sonnet", "haiku"];
    if (wert && namen.indexOf(wert) < 0) namen.push(wert);
    var s = h("select", {}, namen.map(function (n) { return h("option", { value: n, text: n }); }));
    s.value = wert || "opus";
    return s;
  }
  function schalter(text, an, beiAenderung, hilfe) {
    var eingabe = h("input", { type: "checkbox", checked: !!an });
    eingabe.addEventListener("change", function () { beiAenderung(eingabe.checked); });
    return h("label", { class: "schalter", title: hilfe || "" }, eingabe, h("span", { class: "regler" }), h("span", { class: "text", text: text }));
  }
  function zeichnenSystem() {
    var d = S.daten, sys = d.system, p = sys.provider.claude_code || {};
    if (tippt($("#ansicht-system"))) return;
    if (neu("s-anbieter", [p, sys.modelle])) {
      var k = karte("s-anbieter");
      k.appendChild(h("div", { class: "agent" }, h("span", { class: "punkt " + (p.nutzbar ? "ok" : "fehler") }), h("span", { class: "name", text: p.nutzbar ? "Bereit" : "Nicht bereit" }), h("span", { class: "info", title: p.hinweis, text: p.hinweis })));
      k.appendChild(stat("Installiert", p.installiert ? "ja" + (p.version ? " – " + p.version : "") : "nein"));
      k.appendChild(stat("Anmeldung", p.angemeldet ? (p.anmeldeart === "claude.ai" ? "Claude-Abo" + (p.plan ? " (" + p.plan + ")" : "") : String(p.anmeldeart)) : "nicht angemeldet"));
      k.appendChild(h("p", { class: "klein", style: "margin:8px 0", text: "JARVIS nutzt nur die Anmeldung mit deinem Claude-Abo – nie einen API-Schlüssel. Das Prüfen verbraucht kein Kontingent." }));
      k.appendChild(h("button", { type: "button", class: "knopf knopf-klein", text: "Neu prüfen", onclick: function () { tun("POST", "/api/provider/pruefen", {}, "Geprüft."); } }));
    }
    if (neu("s-modelle", [sys.modelle, sys.modell_ausweichen])) {
      var km = karte("s-modelle"), felder = {};
      [["chat", "Gespräch"], ["plan", "Planung"], ["arbeit", "Arbeitsschritte"], ["pruefung", "Prüfschicht"], ["recherche", "Recherche"]].forEach(function (art) {
        felder[art[0]] = modellAuswahl(sys.modelle[art[0]]);
        km.appendChild(h("label", { class: "feld", style: "margin-bottom:8px" }, art[1], felder[art[0]]));
      });
      var ausweichen = h("input", { type: "checkbox", checked: !!sys.modell_ausweichen });
      km.appendChild(h("label", { class: "schalter", style: "margin:4px 0 12px" }, ausweichen, h("span", { class: "regler" }),
        h("span", { class: "text", text: "Bei Abo-Limit sichtbar auf Sonnet ausweichen" })));
      km.appendChild(h("p", { class: "klein", style: "margin-bottom:10px", text: "opus = klügste Antworten, sonnet = schneller und schont dein Limit." }));
      km.appendChild(h("button", { type: "button", class: "knopf knopf-primaer knopf-klein", text: "Modelle speichern", onclick: function () {
        var m = {};
        Object.keys(felder).forEach(function (a) { m[a] = felder[a].value; });
        einstellungSpeichern({ modelle: m, modell_ausweichen: ausweichen.checked });
      } }));
    }
    var st = sys.stimme;
    if (neu("s-stimme", [st, sys.erinnerungen_sprechen])) {
      var ks = karte("s-stimme");
      if (!st.verfuegbar) {
        ks.appendChild(h("p", { class: "fehlertext", text: "Auf diesem Rechner gibt es kein „say“. JARVIS läuft trotzdem, nur ohne Stimme." }));
      } else {
        var wahl = h("select", { "aria-label": "Stimme" }, h("option", { value: "", text: "Automatisch (beste deutsche Stimme)" }),
          st.auswahl.map(function (n) { return h("option", { value: n, text: n }); }));
        wahl.value = st.gewuenscht || "";
        var tempo = h("input", { type: "range", min: "120", max: "260", step: "5", "aria-label": "Sprechtempo" });
        tempo.value = st.tempo;
        var anzeige = h("span", { class: "mono", text: st.tempo + " Wörter/Min." });
        tempo.addEventListener("input", function () { anzeige.textContent = tempo.value + " Wörter/Min."; });
        ks.appendChild(stat("Aktuelle Stimme", st.stimme || "Systemstimme (keine hochwertige gefunden)"));
        ks.appendChild(h("label", { class: "feld", style: "margin:8px 0" }, "Stimme", wahl));
        ks.appendChild(h("label", { class: "feld", style: "margin-bottom:10px" }, h("span", {}, "Tempo: ", anzeige), tempo));
        ks.appendChild(h("div", { class: "knopfreihe", style: "margin-bottom:10px" },
          h("button", { type: "button", class: "knopf knopf-primaer knopf-klein", text: "Speichern", onclick: function () { einstellungSpeichern({ stimme: wahl.value, tempo: parseInt(tempo.value, 10) }); } }),
          h("button", { type: "button", class: "knopf knopf-klein", text: "Probe hören", onclick: function () { sprechen("Hallo, ich bin Jarvis. So klinge ich mit dieser Stimme."); } })));
        ks.appendChild(h("div", { class: "stapel", style: "gap:8px" },
          schalter("Antworten vorlesen", st.vorlesen, function (an) { einstellungSpeichern({ vorlesen: an }); }),
          schalter("Erinnerungen laut sagen", sys.erinnerungen_sprechen, function (an) { einstellungSpeichern({ erinnerungen_sprechen: an }); })));
        ks.appendChild(h("p", { class: "klein", style: "margin-top:10px", text: "Bessere Stimmen: Systemeinstellungen → Bedienungshilfen → Gesprochene Inhalte → Systemstimme → Stimmen verwalten → Deutsch → „Premium“ oder „Erweitert“ laden. JARVIS wählt sie dann automatisch." }));
      }
    }
    if (neu("s-sicherheit", [sys.gesperrt, sys.freigabe_minuten, sys.lan, sys.werkstatt, sys.ordner])) {
      var ksi = karte("s-sicherheit");
      ksi.appendChild(stat("Notstopp", sys.gesperrt ? "AKTIV – JARVIS tut nichts" : "aus"));
      ksi.appendChild(stat("Freigaben gelten", sys.freigabe_minuten + " Minuten, einmalig"));
      ksi.appendChild(stat("Zugang", "nur mit deinem Link (Schlüssel im Cookie)"));
      ksi.appendChild(stat("Erreichbar", sys.lan ? "dieser Mac und dein WLAN" : "nur dieser Mac"));
      ksi.appendChild(stat("Werkstatt", sys.werkstatt));
      ksi.appendChild(stat("Weitere Ordner", sys.ordner.length ? sys.ordner.join(", ") + " (nur lesen)" : "keine"));
      ksi.appendChild(h("p", { class: "klein", style: "margin:8px 0 12px", text: "JARVIS sendet, bezahlt und löscht nichts von sich aus. Alles Verändernde braucht dein Ja unter Freigaben. Das WLAN schaltest du nur im Terminal frei: ./jarvis.sh lan an" }));
      ksi.appendChild(sys.gesperrt
        ? h("button", { type: "button", class: "knopf knopf-primaer", text: "Entsperren", onclick: function () { tun("POST", "/api/entsperren", {}, "Entsperrt."); } })
        : h("button", { type: "button", class: "knopf knopf-gefahr", text: "NOTSTOPP auslösen", onclick: notstopp }));
    }
    if (neu("s-werkzeuge", sys.werkzeuge)) {
      systemProtokolleLaden();
      var kw = karte("s-werkzeuge"), tab = h("div", { class: "tabelle" });
      sys.werkzeuge.forEach(function (w) {
        tab.appendChild(h("div", { class: "zeile" }, h("div", { class: "inhalt" }, h("strong", { text: WERKZEUG_NAMEN[w.name] || w.name }), " ", h("span", { class: "mono klein", text: w.name }),
          h("div", { class: "klein", text: w.beschreibung }), h("div", { class: "chips2" }, badge(w.stufe, w.stufe.indexOf("Freigabe") >= 0 ? "warn" : ""))),
          h("div", { class: "aktionsleiste" }, schalter(w.gesperrt ? "gesperrt" : "erlaubt", !w.gesperrt, function (an) { tun("POST", "/api/werkzeug", { name: w.name, gesperrt: !an }); }, "Ausgeschaltete Werkzeuge kann JARVIS nicht benutzen"))));
      });
      kw.appendChild(tab);
    }
    if (neu("s-daten", [sys.letzte_sicherung, sys.daten_ordner])) {
      var kd = karte("s-daten");
      kd.appendChild(stat("Datenordner", sys.daten_ordner));
      kd.appendChild(stat("Letzte Sicherung", sys.letzte_sicherung ? datum(sys.letzte_sicherung) : "noch keine"));
      kd.appendChild(h("div", { class: "knopfreihe", style: "margin:10px 0" },
        h("button", { type: "button", class: "knopf knopf-klein", text: "Jetzt sichern", onclick: function () { tun("POST", "/api/sicherung", {}, "Gesichert."); } }),
        h("button", { type: "button", class: "knopf knopf-klein", text: "Alles exportieren (JSON)", onclick: exportieren }),
        h("button", { type: "button", class: "knopf knopf-klein", text: "BRAIN.md neu einlesen", title: "Ersetzt die importierten Einträge; deine eigenen bleiben", onclick: function () { tun("POST", "/api/profil/einlesen", {}, "BRAIN.md eingelesen."); } }),
        h("button", { type: "button", class: "knopf knopf-klein", text: "Mac-Umgebung prüfen", onclick: umgebungPruefen })));
      kd.appendChild(h("pre", { id: "umgebung-text", class: "klein vorschau", hidden: true }));
      var bestaetigung = h("input", { type: "text", placeholder: "ALLES LÖSCHEN", "aria-label": "Zur Bestätigung ALLES LÖSCHEN eintippen", autocomplete: "off" });
      var loeschKnopf = h("button", { type: "button", class: "knopf knopf-gefahr knopf-klein", text: "Alles löschen", disabled: true, onclick: function () {
        tun("POST", "/api/alles-loeschen", { bestaetigung: bestaetigung.value }, "Alles gelöscht.");
      } });
      bestaetigung.addEventListener("input", function () { loeschKnopf.disabled = bestaetigung.value !== "ALLES LÖSCHEN"; });
      kd.appendChild(h("div", { class: "formular", style: "margin-top:14px;border-top:1px solid rgba(255,93,79,.3);padding-top:12px" },
        h("p", { class: "klein", text: "Gefahrenbereich: löscht das gesamte Gedächtnis, alle Gespräche, Aufgaben, Aufträge und das Protokoll in der Datenbank. Dateien in der Werkstatt und Sicherungen bleiben. Zum Bestätigen tippe ALLES LÖSCHEN." }),
        bestaetigung, h("div", { class: "knopfreihe" }, loeschKnopf)));
    }
    if (!S.protokolleGebaut) {
      S.protokolleGebaut = true;
      var kp = karte("s-protokolle");
      kp.appendChild(h("div", { class: "knopfreihe", style: "margin-bottom:10px" },
        h("button", { type: "button", class: "knopf knopf-klein", text: "Aktualisieren", onclick: systemProtokolleLaden })));
      kp.appendChild(h("h3", { class: "klein", text: "Audit: wer hat was freigegeben oder ausgeführt" }));
      kp.appendChild(h("div", { class: "log", id: "audit-liste" }));
      kp.appendChild(h("h3", { class: "klein", style: "margin-top:12px", text: "Server-Log" }));
      kp.appendChild(h("div", { class: "log", id: "log-liste" }));
    }
  }
  async function systemProtokolleLaden() {
    if (!S.protokolleGebaut) return;
    var a = await api("GET", "/api/audit?anzahl=60"), l = await api("GET", "/api/logs?anzahl=60");
    var box = leeren($("#audit-liste"));
    var eintraege = (a.daten && a.daten.eintraege) || [];
    if (!eintraege.length) box.appendChild(h("p", { class: "leer", text: "Noch nichts im Audit." }));
    eintraege.forEach(function (e) {
      box.appendChild(h("div", {}, h("span", { class: "z", text: datum(e.zeit) }), h("span", { class: "e", text: e.art }),
        h("span", { class: "d", text: [e.werkzeug, e.bereich, e.ergebnis].filter(Boolean).join(" · ") })));
    });
    var logbox = leeren($("#log-liste"));
    var eintr = ((l.daten && l.daten.eintraege) || []).slice().reverse();
    if (!eintr.length) logbox.appendChild(h("p", { class: "leer", text: "Noch keine Einträge." }));
    eintr.forEach(function (e) {
      var rest = Object.keys(e).filter(function (k) { return ["zeit", "stufe", "ereignis"].indexOf(k) < 0; }).map(function (k) { return k + "=" + kuerzen(JSON.stringify(e[k]), 50); }).join(" ");
      logbox.appendChild(h("div", { class: e.stufe }, h("span", { class: "z", text: fSek.format(parse(e.zeit) || new Date()) }), h("span", { class: "e", text: e.ereignis }), h("span", { class: "d", text: rest })));
    });
  }
  async function exportieren() {
    var r = await api("GET", "/api/export");
    if (r.code !== 200) { meldung(r.daten.fehler || "Export fehlgeschlagen.", true); return; }
    var blob = new Blob([JSON.stringify(r.daten.daten, null, 2)], { type: "application/json" });
    var link = h("a", { href: URL.createObjectURL(blob), download: "jarvis-export-" + new Date().toISOString().slice(0, 10) + ".json" });
    document.body.appendChild(link);
    link.click();
    link.remove();
    meldung("Export gespeichert. Die Datei enthält persönliche Daten – sicher aufbewahren.");
  }
  async function umgebungPruefen() {
    var r = await api("POST", "/api/umgebung", {}), pre = $("#umgebung-text");
    pre.hidden = false;
    pre.textContent = r.daten.text || r.daten.fehler || "Keine Angaben.";
  }
  async function notstopp() {
    await api("POST", "/api/notstopp", {});
    meldung("NOTSTOPP: alles angehalten.", true);
    S.cache = {};
    await laden();
  }

  /* ================================================================ Sprache === */
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var Sprache = { rec: null, modus: null, laeuft: false, pause: false, wartetBis: 0, timer: null };
  var WECKWORT = /^\s*(?:(?:hey|hei|hallo|hi|ok|okay)[\s,]+)?(?:jarvis|jarwis|dscharvis|tscharvis|scharvis)\b[\s,.:;!?-]*/i;

  function sprachHinweis(text, warnung, zwischen) {
    var box = leeren($("#sprach-hinweis"));
    box.className = "sprach-hinweis" + (warnung ? " warn" : "");
    if (zwischen) box.appendChild(h("span", { class: "zwischen", text: "„" + zwischen + "“" }));
    else box.textContent = text || "";
  }
  function mikroZeichnen() {
    var an = Sprache.modus === "einmal" && Sprache.laeuft;
    var knopf = $("#mikro");
    knopf.setAttribute("aria-pressed", an ? "true" : "false");
    knopf.setAttribute("aria-label", an ? "Zuhören beenden" : "Einmal zuhören");
    $("#hey-jarvis").checked = Sprache.modus === "dauer";
  }
  function sprachFehlt() {
    if (!SR) { sprachHinweis("Dieser Browser erkennt keine Sprache. Auf dem Mac gehen Safari und Chrome.", true); return true; }
    if (!window.isSecureContext) {
      sprachHinweis("Spracheingabe geht nur direkt auf dem Mac (Adresse 127.0.0.1). Auf dem Handy bitte tippen oder die Diktierfunktion der Tastatur nutzen.", true);
      return true;
    }
    return false;
  }
  function erkennerAnwerfen() {
    if (Sprache.rec || Sprache.pause || !Sprache.modus) return;
    var rec = new SR();
    rec.lang = "de-DE";
    rec.interimResults = true;
    rec.continuous = Sprache.modus === "dauer";
    rec.maxAlternatives = 1;
    rec.onstart = function () { Sprache.laeuft = true; mikroZeichnen(); kernSetzen(); if (Sprache.modus === "einmal") sprachHinweis("Ich höre zu …"); else sprachHinweis("„Hey Jarvis“ ist an. Sag zum Beispiel: „Hey Jarvis, was steht heute an?“"); };
    rec.onresult = sprachErgebnis;
    rec.onerror = sprachFehler;
    rec.onend = function () {
      Sprache.rec = null;
      Sprache.laeuft = false;
      if (Sprache.modus === "einmal") Sprache.modus = null;
      mikroZeichnen();
      kernSetzen();
      if (Sprache.modus === "dauer" && !Sprache.pause) {
        window.clearTimeout(Sprache.timer);
        Sprache.timer = window.setTimeout(erkennerAnwerfen, 400);
      } else if (!Sprache.modus && !$("#sprach-hinweis").classList.contains("warn")) {
        sprachHinweis("");
      }
    };
    Sprache.rec = rec;
    try { rec.start(); } catch (e) { Sprache.rec = null; sprachHinweis("Die Spracherkennung ließ sich nicht starten.", true); }
  }
  function sprachFehler(e) {
    var art = e && e.error;
    if (art === "no-speech" || art === "aborted") return; // Pause ist normal; onend startet bei Bedarf neu
    var texte = {
      "not-allowed": "Das Mikrofon ist nicht erlaubt. Erlaube es für diese Seite in den Browser-Einstellungen und klick dann nochmal.",
      "service-not-allowed": "Der Browser erlaubt die Spracherkennung hier nicht. Erlaube sie in den Browser-Einstellungen.",
      "audio-capture": "Es wurde kein Mikrofon gefunden.",
      "network": "Die Spracherkennung braucht eine Internetverbindung zum Anbieter deines Browsers (Safari: Apple, Chrome: Google)."
    };
    sprachHinweis(texte[art] || "Spracherkennung gestoppt (" + art + ").", true);
    Sprache.modus = null;
    schreiben("jv_hey", "0");
    mikroZeichnen();
  }
  function sprachErgebnis(e) {
    var zwischen = "";
    for (var i = e.resultIndex; i < e.results.length; i++) {
      var r = e.results[i], text = r[0].transcript;
      if (r.isFinal) sprachGehoert(text); else zwischen += text;
    }
    if (zwischen) sprachHinweis("", false, zwischen);
  }
  function sprachGehoert(text) {
    text = (text || "").trim();
    if (!text) return;
    if (Sprache.modus === "einmal") {
      Sprache.modus = null;
      try { Sprache.rec.stop(); } catch (e) { /* war schon beendet */ }
      sprachHinweis("");
      senden(text);
      return;
    }
    var treffer = WECKWORT.exec(text);
    if (treffer) {
      var rest = text.slice(treffer[0].length).trim();
      if (rest) { Sprache.wartetBis = 0; sprachHinweis(""); senden(rest); }
      else { Sprache.wartetBis = Date.now() + 9000; sprachHinweis("Ich höre …"); kernSetzen(); }
      return;
    }
    if (Sprache.wartetBis && Date.now() < Sprache.wartetBis) { Sprache.wartetBis = 0; sprachHinweis(""); senden(text); }
    /* sonst: nicht angesprochen - ignorieren */
  }
  function sprachStoppen() {
    Sprache.modus = null;
    Sprache.wartetBis = 0;
    window.clearTimeout(Sprache.timer);
    if (Sprache.rec) { try { Sprache.rec.abort(); } catch (e) { /* schon beendet */ } }
    Sprache.rec = null;
    Sprache.laeuft = false;
    mikroZeichnen();
    kernSetzen();
  }
  function sprachModus(modus) {
    if (sprachFehlt()) { mikroZeichnen(); return; }
    var war = Sprache.modus;
    sprachStoppen();
    if (modus === war || !modus) { schreiben("jv_hey", "0"); sprachHinweis(""); return; }
    Sprache.modus = modus;
    schreiben("jv_hey", modus === "dauer" ? "1" : "0");
    erkennerAnwerfen();
  }
  /* Während JARVIS spricht, hört er nicht zu (sonst würde er sich selbst verstehen). */
  function sprachePausePruefen() {
    var spricht = !!(S.daten && S.daten.system.stimme.spricht);
    if (spricht && !Sprache.pause && Sprache.modus) {
      Sprache.pause = true;
      if (Sprache.rec) { try { Sprache.rec.abort(); } catch (e) { /* schon beendet */ } Sprache.rec = null; Sprache.laeuft = false; }
      kernSetzen();
    } else if (!spricht && Sprache.pause) {
      Sprache.pause = false;
      window.clearTimeout(Sprache.timer);
      Sprache.timer = window.setTimeout(erkennerAnwerfen, 700);
    }
  }
  function sprachBauen() {
    $("#mikro").appendChild(icon("mikro"));
    $("#mikro").addEventListener("click", function () { sprachModus("einmal"); });
    $("#hey-jarvis").addEventListener("change", function () { sprachModus(this.checked ? "dauer" : null); });
    $("#vorlesen").addEventListener("change", function () { einstellungSpeichern({ vorlesen: this.checked }, this.checked ? "Antworten werden vorgelesen." : "Vorlesen aus."); });
    $("#still").addEventListener("click", function () { api("POST", "/api/still", {}).then(function () { laden(); }); });
    if (!SR) sprachHinweis("Spracheingabe: dieser Browser unterstützt sie nicht. Tippen geht immer.", false);
    else sprachHinweis("Die Spracherkennung macht dein Browser (Safari: Apple, Chrome: Google), nicht JARVIS. Sie hört nur, solange sie an ist.");
    if (SR && window.isSecureContext && lesen("jv_hey") === "1") { Sprache.modus = "dauer"; erkennerAnwerfen(); }
  }

  /* ================================================================== Start === */
  function zeichnen() {
    var d = S.daten;
    zeichnenKopf();
    if (!d) { kernSetzen(); return; }
    zeichnenReiterZeichen();
    var st = d.system.stimme;
    $("#vorlesen").checked = !!st.vorlesen;
    $("#vorlesen").disabled = !st.verfuegbar;
    sprachePausePruefen();
    kernSetzen();
    var a = S.ansicht;
    if (a === "jarvis") { zeichnenChat(); zeichnenFreigaben($("#freigaben-inline"), "j-freigaben", ""); zeichnenMini(); }
    else if (a === "leitstand") zeichnenLeitstand();
    else if (a === "auftraege") zeichnenAuftraege();
    else if (a === "wissen") zeichnenWissen();
    else if (a === "system") zeichnenSystem();
  }

  function start() {
    reiterBauen();
    eingabeBauen();
    planFormBauen();
    wissenFormenBauen();
    sprachBauen();
    $("#notstopp").addEventListener("click", notstopp);
    $("#entsperren").addEventListener("click", function () { tun("POST", "/api/entsperren", {}, "Entsperrt."); });
    if (window.JarvisKern) kern = window.JarvisKern.start($("#kern"));
    ansichtWechseln(S.ansicht);
    laden().then(pollenPlanen, pollenPlanen);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) laden().then(pollenPlanen, pollenPlanen); });
    window.setInterval(function () { S.cache["kopf-chips"] = null; if (S.daten) zeichnenKopf(); }, 30000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
