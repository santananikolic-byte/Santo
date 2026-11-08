// JARVIS: Kalender ueber EventKit (JavaScript for Automation). Nur JARVIS ruft dieses Skript auf (jarvis_core/kalender.py):
//   osascript -l JavaScript kalender.js JARVIS termine VON BIS
//   osascript -l JavaScript kalender.js JARVIS suchen VON BIS TEXT
//   osascript -l JavaScript kalender.js JARVIS eintragen TITEL BEGINN ENDE 0|1 ORT NOTIZ KALENDER EXTRAS-JSON
//   osascript -l JavaScript kalender.js JARVIS details ID BEGINN
//   osascript -l JavaScript kalender.js JARVIS aendern ID BEGINN 0|1 AENDERUNGEN-JSON
//   osascript -l JavaScript kalender.js JARVIS loeschen ID BEGINN 0|1
// Nutzertext kommt nur ueber argv (auch als JSON, das nur gelesen, nie ausgefuehrt wird), nie in den Skripttext.
// Ausgabe: genau eine Zeile JSON, nur ASCII. Serientermine liefert EventKit einzeln; ein Termin einer Serie wird ueber
// seine Kennung (eventIdentifier) und seinen Beginn gefunden. 0|1 = nur dieser Termin | dieser und alle folgenden.
// Aendern und Loeschen ruft JARVIS nur nach der Freigabe des Nutzers auf. Teilnehmer gibt es nicht (EventKit kann
// niemanden einladen).
// Beim ersten Aufruf fragt macOS (fuer das Terminal) nach dem Kalender - noetig ist "Vollzugriff".
ObjC.import("Foundation");
ObjC.import("EventKit");

var EREIGNIS = 0, OFFEN = 0, VOLL = 3, NUR_HINZUFUEGEN = 4;

function u(x) { return ObjC.unwrap(x); }
function text(x) { var t = u(x); return (t === undefined || t === null) ? "" : String(t); }
function status() { return Number($.EKEventStore.authorizationStatusForEntityType(EREIGNIS)); }

// Erlaubnis pruefen und beim ersten Mal erfragen. Die Antwort kommt ueber einen Block, der nicht immer verlaesslich
// feuert - darum wird zusaetzlich der Status abgefragt.
function zugriff(store, sekunden) {
  var s0 = status();
  if (s0 === VOLL) return null;
  if (s0 !== OFFEN && s0 !== NUR_HINZUFUEGEN) return "zugriff_verweigert";
  var fertig = false;
  var antwort = function (ok, fehler) { fertig = true; };
  if (store.respondsToSelector($.NSSelectorFromString($("requestFullAccessToEventsWithCompletion:")))) {
    store.requestFullAccessToEventsWithCompletion(antwort);  // macOS 14 und neuer
  } else {
    store.requestAccessToEntityTypeCompletion(EREIGNIS, antwort);  // macOS 13
  }
  var bis = Date.now() + sekunden * 1000;
  while (!fertig && status() === s0 && Date.now() < bis) {
    $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.2));
  }
  var s = status();
  if (s === VOLL) { store.reset; return null; }  // nach frischer Erlaubnis neu laden
  if (s === NUR_HINZUFUEGEN) return "nur_hinzufuegen";
  if (s === OFFEN) return "zugriff_offen";
  return "zugriff_verweigert";
}

// Datum: streng als Ortszeit lesen (nie ueber Texte, die von der Spracheinstellung abhaengen)
function lokal(s) {
  var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/.exec(s || "");
  if (!m) { throw new Error("datum"); }
  var d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6], 0);
  if (d.getFullYear() !== +m[1] || d.getMonth() !== +m[2] - 1 || d.getDate() !== +m[3] ||
      d.getHours() !== +m[4] || d.getMinutes() !== +m[5]) {
    throw new Error("datum");  // gibt es nicht (31.02.) oder faellt in die Zeitumstellung
  }
  return d;
}
function ns(d) { return $.NSDate.dateWithTimeIntervalSince1970(d.getTime() / 1000); }
function zwei(n) { return (n < 10 ? "0" : "") + n; }
function iso(d) {
  return d.getFullYear() + "-" + zwei(d.getMonth() + 1) + "-" + zwei(d.getDate()) + "T" + zwei(d.getHours()) + ":" +
    zwei(d.getMinutes()) + ":" + zwei(d.getSeconds());
}
function aus(o) {
  return JSON.stringify(o).replace(/[\u007f-\uffff]/g, function (c) {
    return "\\u" + ("000" + c.charCodeAt(0).toString(16)).slice(-4);
  });
}

function kalenderliste(store) {
  var alle = store.calendarsForEntityType(EREIGNIS), liste = [];
  for (var i = 0; i < Number(alle.count); i++) {
    var k = alle.objectAtIndex(i);
    liste.push({name: text(k.title), schreibbar: !!u(k.allowsContentModifications), k: k});
  }
  return liste;
}

var HAEUFIGKEIT = {taeglich: 0, woechentlich: 1, monatlich: 2, jaehrlich: 3};
var NAME_HAEUFIGKEIT = ["taeglich", "woechentlich", "monatlich", "jaehrlich"];

function regel_von(e) {  // die Wiederholung einer Serie (fuer die Sicherung vor dem Loeschen)
  if (!u(e.hasRecurrenceRules)) { return null; }
  var regeln = e.recurrenceRules;
  if (!regeln || Number(regeln.count) === 0) { return null; }
  var r = regeln.objectAtIndex(0), ende = r.recurrenceEnd, bis = "", anzahl = 0;
  if (ende && !ende.isNil()) {
    var datum = u(ende.endDate);
    if (datum) { bis = iso(datum); } else { anzahl = Number(ende.occurrenceCount); }
  }
  return {wiederholen: NAME_HAEUFIGKEIT[Number(r.frequency)] || "", intervall: Number(r.interval), bis: bis, anzahl: anzahl};
}

function erinnerungen_von(e) {
  var alarme = e.alarms, liste = [];
  if (alarme && !alarme.isNil()) {
    for (var i = 0; i < Number(alarme.count); i++) {
      liste.push(Math.round(-Number(alarme.objectAtIndex(i).relativeOffset) / 60));
    }
  }
  return liste;
}

function daten(e, voll) {
  var beginn = u(e.startDate), d = {t: beginn.getTime(), titel: text(e.title), beginn: iso(beginn),
    ende: iso(u(e.endDate)), ganztag: !!u(e.allDay), ort: text(e.location), kalender: text(e.calendar.title),
    id: text(e.eventIdentifier), serie: !!u(e.hasRecurrenceRules), notiz: text(e.notes).slice(0, voll ? 4000 : 500)};
  if (voll) { d.regel = regel_von(e); d.erinnerungen = erinnerungen_von(e); }
  return d;
}

function liste_von(store, von, bis, filter) {
  var alle = store.calendarsForEntityType(EREIGNIS);
  var treffer = store.eventsMatchingPredicate(
    store.predicateForEventsWithStartDateEndDateCalendars(ns(lokal(von)), ns(lokal(bis)), alle));
  var liste = [];
  for (var i = 0; i < Number(treffer.count) && liste.length < 2000; i++) {
    var d = daten(treffer.objectAtIndex(i), false);
    if (!filter || filter(d)) { liste.push(d); }
  }
  liste.sort(function (a, b) { return a.t - b.t; });  // EventKit liefert unsortiert
  liste = liste.slice(0, 300);
  liste.forEach(function (x) { delete x.t; });
  return liste;
}

function suchen(store, von, bis, wort) {
  var w = String(wort || "").toLowerCase();
  if (w.length < 2) { return {fehler: "suchwort"}; }
  return {termine: liste_von(store, von, bis, function (d) {
    return (d.titel + "\n" + d.ort + "\n" + d.notiz).toLowerCase().indexOf(w) >= 0;
  })};
}

// Einen Termin (auch einen einzelnen einer Serie) ueber Kennung und Beginn finden
function finde(store, id, beginn) {
  var b = lokal(beginn), alle = store.calendarsForEntityType(EREIGNIS);
  var treffer = store.eventsMatchingPredicate(store.predicateForEventsWithStartDateEndDateCalendars(
    ns(new Date(b.getTime() - 60000)), ns(new Date(b.getTime() + 60000)), alle));
  for (var i = 0; i < Number(treffer.count); i++) {
    var e = treffer.objectAtIndex(i);
    if (text(e.eventIdentifier) === id && Math.abs(u(e.startDate).getTime() - b.getTime()) < 1000) { return e; }
  }
  return null;
}

function kalender_nach_name(store, name) {
  var treffer = kalenderliste(store).filter(function (k) { return k.name === name; });
  if (treffer.length === 0) { return {fehler: "kalender_unbekannt"}; }
  if (treffer.length > 1) { return {fehler: "kalender_mehrdeutig"}; }
  if (!treffer[0].schreibbar) { return {fehler: "nur_lesen"}; }
  return {k: treffer[0].k};
}

function erinnerung_setzen(e, minuten) {
  e.alarms = $.NSArray.array;
  if (minuten !== null && minuten !== undefined && minuten !== "" && Number(minuten) >= 0) {
    e.addAlarm($.EKAlarm.alarmWithRelativeOffset(-60 * Number(minuten)));
  }
}

function termine(store, von, bis) {
  var liste = liste_von(store, von, bis, null);
  var standard = store.defaultCalendarForNewEvents;
  return {termine: liste, standard: (standard && !standard.isNil()) ? text(standard.title) : "",
          kalender: kalenderliste(store).map(function (k) { return {name: k.name, schreibbar: k.schreibbar}; })};
}

function eintragen(store, a) {  // a = [titel, beginn, ende, ganztag, ort, notiz, kalender, extras-json]
  var ziel = null, name = a[6] || "", extras = a[7] ? JSON.parse(a[7]) : {};
  if (name) {
    var gefunden = kalender_nach_name(store, name);
    if (gefunden.fehler) { return gefunden; }
    ziel = gefunden.k;
  } else {
    ziel = store.defaultCalendarForNewEvents;
    if (!ziel || ziel.isNil()) { return {fehler: "kein_kalender"}; }
    if (!u(ziel.allowsContentModifications)) { return {fehler: "nur_lesen"}; }
  }
  var beginn = lokal(a[1]), ende = lokal(a[2]);
  if (ende <= beginn) { return {fehler: "datum"}; }
  var e = $.EKEvent.eventWithEventStore(store);
  e.calendar = ziel;
  e.title = a[0];
  e.startDate = ns(beginn);
  e.endDate = ns(ende);
  e.allDay = (a[3] === "1");
  if (a[4]) { e.location = a[4]; }
  if (a[5]) { e.notes = a[5]; }
  if (extras.erinnerung !== undefined && extras.erinnerung !== null) { erinnerung_setzen(e, extras.erinnerung); }
  var serie = false;
  if (extras.wiederholen) {
    if (!(extras.wiederholen in HAEUFIGKEIT)) { return {fehler: "wiederholen"}; }
    var ende_serie = null;
    if (extras.bis) { ende_serie = $.EKRecurrenceEnd.recurrenceEndWithEndDate(ns(lokal(extras.bis))); }
    else if (extras.anzahl) { ende_serie = $.EKRecurrenceEnd.recurrenceEndWithOccurrenceCount(Number(extras.anzahl)); }
    e.addRecurrenceRule($.EKRecurrenceRule.alloc.initRecurrenceWithFrequencyIntervalEnd(
      HAEUFIGKEIT[extras.wiederholen], Number(extras.intervall || 1), ende_serie));
    serie = true;
  }
  var fehler = Ref();
  if (!store.saveEventSpanError(e, serie ? $.EKSpanFutureEvents : $.EKSpanThisEvent, fehler)) {
    return {fehler: "speichern"};
  }
  return {ok: true, kalender: text(ziel.title), id: text(e.eventIdentifier)};
}

function details(store, id, beginn) {
  var e = finde(store, id, beginn);
  if (!e) { return {fehler: "nicht_gefunden"}; }
  var d = daten(e, true);
  delete d.t;
  d.schreibbar = !!u(e.calendar.allowsContentModifications);
  return {termin: d};
}

function aendern(store, id, beginn, span, aenderungen) {  // nur nach Freigabe des Nutzers
  var e = finde(store, id, beginn);
  if (!e) { return {fehler: "nicht_gefunden"}; }
  if (!u(e.calendar.allowsContentModifications)) { return {fehler: "nur_lesen"}; }
  var a = JSON.parse(aenderungen || "{}"), vorher = daten(e, true);
  if (a.kalender) {
    var gefunden = kalender_nach_name(store, a.kalender);
    if (gefunden.fehler) { return gefunden; }
    e.calendar = gefunden.k;
  }
  if (a.titel !== undefined) { e.title = a.titel; }
  if (a.ort !== undefined) { e.location = a.ort; }
  if (a.notiz !== undefined) { e.notes = a.notiz; }
  if (a.ganztag !== undefined) { e.allDay = !!a.ganztag; }
  if (a.beginn !== undefined) {
    var b = lokal(a.beginn), en = lokal(a.ende);
    if (en <= b) { return {fehler: "datum"}; }
    e.startDate = ns(b);
    e.endDate = ns(en);
  }
  if (a.erinnerung !== undefined) { erinnerung_setzen(e, a.erinnerung); }
  var fehler = Ref();
  if (!store.saveEventSpanError(e, span === "1" ? $.EKSpanFutureEvents : $.EKSpanThisEvent, fehler)) {
    return {fehler: "speichern"};
  }
  var nachher = daten(e, true);
  delete vorher.t;
  delete nachher.t;
  return {ok: true, vorher: vorher, nachher: nachher};
}

function loeschen(store, id, beginn, span) {  // nur nach Freigabe des Nutzers; JARVIS sichert vorher (details)
  var e = finde(store, id, beginn);
  if (!e) { return {fehler: "nicht_gefunden"}; }
  if (!u(e.calendar.allowsContentModifications)) { return {fehler: "nur_lesen"}; }
  var fehler = Ref();
  if (!store.removeEventSpanError(e, span === "1" ? $.EKSpanFutureEvents : $.EKSpanThisEvent, fehler)) {
    return {fehler: "loeschen"};
  }
  return {ok: true};
}

function run(argv) {
  try {
    if (argv[0] !== "JARVIS") { return aus({fehler: "aufruf"}); }
    var store = $.EKEventStore.alloc.init;
    var problem = zugriff(store, 90);
    if (problem) { return aus({fehler: problem}); }
    if (argv[1] === "termine") { return aus(termine(store, argv[2], argv[3])); }
    if (argv[1] === "suchen") { return aus(suchen(store, argv[2], argv[3], argv[4])); }
    if (argv[1] === "eintragen") { return aus(eintragen(store, argv.slice(2))); }
    if (argv[1] === "details") { return aus(details(store, argv[2], argv[3])); }
    if (argv[1] === "aendern") { return aus(aendern(store, argv[2], argv[3], argv[4], argv[5])); }
    if (argv[1] === "loeschen") { return aus(loeschen(store, argv[2], argv[3], argv[4])); }
    return aus({fehler: "aufruf"});
  } catch (x) {
    var nachricht = String((x && x.message) || x);
    return aus({fehler: nachricht === "datum" ? "datum" : "skript", text: nachricht.slice(0, 300)});
  }
}
