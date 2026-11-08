// JARVIS: Kalender ueber EventKit (JavaScript for Automation). Nur JARVIS ruft dieses Skript auf (jarvis_core/kalender.py):
//   osascript -l JavaScript kalender.js JARVIS termine 2026-11-09T00:00:00 2026-11-16T00:00:00
//   osascript -l JavaScript kalender.js JARVIS eintragen TITEL BEGINN ENDE 0|1 ORT NOTIZ KALENDER
// Nutzertext kommt nur ueber argv, nie in den Skripttext. Ausgabe: genau eine Zeile JSON, nur ASCII.
// Serientermine liefert EventKit einzeln. Teilnehmer, Aendern und Loeschen gibt es hier bewusst nicht.
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

function termine(store, von, bis) {
  var alle = store.calendarsForEntityType(EREIGNIS);
  var treffer = store.eventsMatchingPredicate(
    store.predicateForEventsWithStartDateEndDateCalendars(ns(lokal(von)), ns(lokal(bis)), alle));
  var liste = [];
  for (var i = 0; i < Number(treffer.count) && i < 2000; i++) {
    var e = treffer.objectAtIndex(i), beginn = u(e.startDate);
    liste.push({t: beginn.getTime(), titel: text(e.title), beginn: iso(beginn), ende: iso(u(e.endDate)),
                ganztag: !!u(e.allDay), ort: text(e.location), kalender: text(e.calendar.title)});
  }
  liste.sort(function (a, b) { return a.t - b.t; });  // EventKit liefert unsortiert
  liste = liste.slice(0, 300);
  liste.forEach(function (x) { delete x.t; });
  var standard = store.defaultCalendarForNewEvents;
  return {termine: liste, standard: (standard && !standard.isNil()) ? text(standard.title) : "",
          kalender: kalenderliste(store).map(function (k) { return {name: k.name, schreibbar: k.schreibbar}; })};
}

function eintragen(store, a) {  // a = [titel, beginn, ende, ganztag, ort, notiz, kalender]
  var ziel = null, name = a[6] || "";
  if (name) {
    var treffer = kalenderliste(store).filter(function (k) { return k.name === name; });
    if (treffer.length === 0) { return {fehler: "kalender_unbekannt"}; }
    if (treffer.length > 1) { return {fehler: "kalender_mehrdeutig"}; }
    if (!treffer[0].schreibbar) { return {fehler: "nur_lesen"}; }
    ziel = treffer[0].k;
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
  var fehler = Ref();
  if (!store.saveEventSpanError(e, $.EKSpanThisEvent, fehler)) { return {fehler: "speichern"}; }
  return {ok: true, kalender: text(ziel.title)};
}

function run(argv) {
  try {
    if (argv[0] !== "JARVIS") { return aus({fehler: "aufruf"}); }
    var store = $.EKEventStore.alloc.init;
    var problem = zugriff(store, 90);
    if (problem) { return aus({fehler: problem}); }
    if (argv[1] === "termine") { return aus(termine(store, argv[2], argv[3])); }
    if (argv[1] === "eintragen") { return aus(eintragen(store, argv.slice(2))); }
    return aus({fehler: "aufruf"});
  } catch (x) {
    var nachricht = String((x && x.message) || x);
    return aus({fehler: nachricht === "datum" ? "datum" : "skript", text: nachricht.slice(0, 300)});
  }
}
