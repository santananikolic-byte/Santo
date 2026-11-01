// Prüft die Oberfläche im echten Browser (Chromium über Playwright):
// keine JavaScript-Fehler, alle Ansichten, Gespräch, Freigabe, Auftrag, Gedächtnis, Notstopp, Bereichstrennung, Handy-Ansicht.
// Nur für die Entwicklung (braucht Node und Playwright); der Alltag auf dem Mac braucht beides nicht.
//
//   node tests/ui/ui_pruefung.js [Ausgabeordner für Bildschirmfotos]
//
// Der Server läuft dabei abgeschottet mit Ersatz-Claude (tests/ui/server_fuer_ui.py).
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PY = process.env.JARVIS_PYTHON || "python3";
const OUT = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), "jarvis_ui_fotos_"));
fs.mkdirSync(OUT, { recursive: true });
const fehler = [];
function pruefe(bedingung, text) {
  if (bedingung) console.log("  ok: " + text);
  else { fehler.push(text); console.log("  FEHLER: " + text); }
}

function serverStarten() {
  return new Promise((resolve, reject) => {
    const kind = spawn(PY, [path.join(__dirname, "server_fuer_ui.py")], { stdio: ["ignore", "pipe", "inherit"] });
    let puffer = "";
    kind.stdout.on("data", (d) => {
      puffer += d;
      if (puffer.includes("\n")) {
        try { resolve({ kind, info: JSON.parse(puffer.split("\n")[0]) }); } catch (e) { reject(e); }
      }
    });
    kind.on("exit", (code) => reject(new Error("Server beendet (Code " + code + ")")));
  });
}
function warteAufServer(port) {
  return new Promise((resolve, reject) => {
    const ende = Date.now() + 20000;
    (function versuche() {
      http.get({ host: "127.0.0.1", port, path: "/status", timeout: 1000 }, (r) => { r.resume(); resolve(); })
        .on("error", () => (Date.now() > ende ? reject(new Error("Server antwortet nicht")) : setTimeout(versuche, 200)));
    })();
  });
}
const foto = (page, name) => page.screenshot({ path: path.join(OUT, name) });
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const { kind, info } = await serverStarten();
  const basis = "http://127.0.0.1:" + info.port;
  await warteAufServer(info.port);
  const werkstatt = path.join(info.ordner, "werkstatt");
  const browser = await chromium.launch();
  const meldungen = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "de-DE", timezoneId: "Europe/Berlin" });
    await context.addCookies([{ name: "jv_token", value: info.token, url: basis }]);
    // Ersatz für die Spracherkennung des Browsers: so lässt sich die Logik hinter „Hey Jarvis“ prüfen, ohne Mikrofon.
    await context.addInitScript(() => {
      window.__erkenner = null;
      class ErsatzErkenner {
        constructor() { this.continuous = false; this.interimResults = false; this.lang = ""; window.__erkenner = this; }
        start() { setTimeout(() => this.onstart && this.onstart(), 10); }
        stop() { setTimeout(() => this.onend && this.onend(), 10); }
        abort() { setTimeout(() => this.onend && this.onend(), 10); }
      }
      window.SpeechRecognition = ErsatzErkenner;
      window.__hoere = (text, endgueltig) => {
        const r = [{ transcript: text }];
        r.isFinal = endgueltig !== false;
        window.__erkenner.onresult({ resultIndex: 0, results: [r] });
      };
    });
    const page = await context.newPage();
    page.on("console", (m) => { if (["error", "warning"].includes(m.type())) meldungen.push(m.type() + ": " + m.text()); });
    page.on("pageerror", (e) => meldungen.push("pageerror: " + e.message));
    page.on("requestfailed", (r) => meldungen.push("requestfailed: " + r.url()));

    console.log("Start und Jarvis-Ansicht");
    await page.goto(basis + "/");
    await page.waitForSelector("#reiter button");
    pruefe((await page.locator("#reiter button").count()) === 5, "fünf Reiter");
    pruefe((await page.title()) === "JARVIS", "Titel JARVIS");
    await page.waitForFunction(() => document.querySelector("#chips").textContent.includes("bereit"), null, { timeout: 20000 });
    pruefe(true, "Claude Code wird als bereit angezeigt");
    pruefe((await page.locator("#kern-zustand").textContent()) === "bereit", "Kern zeigt „bereit“");
    const kernPixel = await page.evaluate(() => {
      const c = document.querySelector("#kern"), x = c.getContext("2d");
      const d = x.getImageData(0, 0, c.width, c.height).data;
      let hell = 0;
      for (let i = 3; i < d.length; i += 4 * 17) if (d[i] > 40) hell++;
      return hell;
    });
    pruefe(kernPixel > 200, "der Kern wird wirklich gezeichnet (" + kernPixel + " Messpunkte)");

    console.log("Gespräch");
    await page.fill("#text", "Hallo Jarvis");
    await page.press("#text", "Enter");
    await page.waitForSelector(".nachricht.jarvis .blase:has-text('Ich bin JARVIS')", { timeout: 20000 });
    pruefe((await page.locator(".nachricht.nutzer .blase").first().textContent()) === "Hallo Jarvis", "eigene Nachricht steht im Verlauf");
    pruefe((await page.locator("#text").inputValue()) === "", "Eingabefeld wurde geleert");
    await pause(900);
    await foto(page, "01-jarvis-desktop.png");

    console.log("Schnellstart-Knöpfe");
    await page.click(".schnell-knopf:text-is('Firma prüfen')");
    pruefe((await page.locator("#text").inputValue()).startsWith("Prüfe diese Firma"), "„Firma prüfen“ füllt nur das Eingabefeld vor (sendet nichts)");
    await page.fill("#text", "");
    await page.click(".schnell-knopf:text-is('Tagesbriefing')");
    await page.waitForSelector(".nachricht.nutzer .blase:has-text('Tagesbriefing')", { timeout: 15000 });
    await page.waitForFunction(() => !document.querySelector(".nachricht.denkt"), null, { timeout: 15000 });
    pruefe(true, "„Tagesbriefing“ sendet die Frage und JARVIS antwortet");
    await page.click(".schnell-knopf:text-is('Akquise starten')");
    await page.waitForSelector(".nachricht.nutzer .blase:has-text('Ausschreibungsportale')", { timeout: 15000 });
    await page.waitForFunction(() => !document.querySelector(".nachricht.denkt"), null, { timeout: 15000 });
    pruefe(true, "„Akquise starten“ sendet die Suche los und JARVIS antwortet");

    console.log("Verbindungsabbruch");
    await page.route("**/api/anfrage", (route) => route.abort());
    await page.fill("#text", "Diese Nachricht darf nicht verloren gehen");
    await page.press("#text", "Enter");
    await page.waitForFunction(() => document.querySelector("#text").value.includes("nicht verloren gehen"), null, { timeout: 20000 });
    pruefe(true, "bei Verbindungsabbruch steht der Text wieder im Eingabefeld");
    await page.unroute("**/api/anfrage");
    meldungen.length = 0; // der absichtlich abgebrochene Aufruf erscheint in der Konsole - das ist hier gewollt
    await page.fill("#text", "");

    console.log("Freigabe");
    await page.fill("#text", "Aktualisiere a.md");
    await page.press("#text", "Enter");
    await page.waitForSelector(".freigabe", { timeout: 20000 });
    pruefe((await page.locator(".freigabe .vorschau").textContent()).includes("ÜBERSCHRIEBEN"), "Freigabe zeigt die Vorschau mit Überschreib-Hinweis");
    pruefe(fs.readFileSync(path.join(werkstatt, "a.md"), "utf8") === "alter Inhalt", "vor dem Ja ist die Datei unverändert");
    pruefe((await page.locator("#reiter-jarvis .zeichen").textContent()) === "1", "Reiter zeigt die offene Freigabe");
    await foto(page, "02-freigabe.png");
    await page.getByRole("button", { name: "Ja, ausführen" }).click();
    await page.waitForSelector("#toast.sichtbar:has-text('Ausgeführt')", { timeout: 10000 });
    await page.waitForFunction(() => !document.querySelector(".freigabe"));
    pruefe(fs.readFileSync(path.join(werkstatt, "a.md"), "utf8") === "neuer Inhalt", "nach dem Ja ist die Datei geändert");
    pruefe((await page.locator(".nachricht.ereignis").last().textContent()).includes("Freigabe"), "das Ergebnis steht als Ereignis im Gespräch");

    console.log("Leitstand");
    await page.click("#reiter-leitstand");
    await page.waitForSelector("#k-anfragen svg.balken");
    pruefe((await page.locator("#k-agenten .agent").count()) === 7, "Agenten: Orchestrator plus sechs Rollen");
    pruefe((await page.locator("#k-agenten").textContent()).includes("bisher nicht gebraucht"), "Rollen ohne Einsatz sind ehrlich als „nicht gebraucht“ markiert");
    pruefe((await page.locator("#k-heute").textContent()).includes("Modellaufrufe"), "Verbrauchskarte zeigt Modellaufrufe");
    pruefe((await page.locator("#k-log .log div").count()) > 3, "Ereignisse stammen aus dem echten Log");
    await pause(300);
    await foto(page, "03-leitstand.png");

    console.log("Aufträge");
    await page.click("#reiter-auftraege");
    await page.fill("#plan-ziel", "Erstelle eine Checkliste, mit der wir neue Firmen vor einem Auftrag prüfen.");
    await page.click("#plan-knopf");
    await page.waitForSelector(".auftrag:has-text('Prüfliste für neue Firmen')", { timeout: 30000 });
    pruefe((await page.locator(".auftrag .badge").first().textContent()) === "Entwurf", "neuer Auftrag ist nur ein Entwurf");
    pruefe((await page.locator("#plan-ergebnis").textContent()).includes("nur Entwurf"), "der Plan sagt ausdrücklich „nur Entwurf“");
    await page.locator(".auftrag summary").first().click();
    pruefe((await page.locator(".auftrag .schritt .koerper").first().textContent()).includes("Handelsregister"), "Schritt zeigt Kriterium");
    await page.getByRole("button", { name: "Starten" }).click();
    await page.waitForSelector(".auftrag .badge.b-fertig", { timeout: 40000 });
    pruefe(fs.existsSync(path.join(werkstatt, "notizen", "pruefliste.md")), "der Schritt hat die Datei wirklich geschrieben");
    pruefe((await page.locator(".auftrag .schritt .koerper").first().textContent()).includes("Prüfschicht"), "Prüfschicht-Ergebnis ist sichtbar");
    await pause(300);
    await foto(page, "04-auftraege.png");

    console.log("Wissen");
    await page.click("#reiter-wissen");
    await page.waitForSelector("#fakten-liste .zeile");
    pruefe((await page.locator("#fakten-liste").textContent()).includes("Familienbetrieb"), "Geschäftswissen ist sichtbar");
    pruefe(!(await page.locator("#fakten-liste").textContent()).includes("500.000"), "private Ziele sind im Geschäftsbereich ausgeblendet");
    await page.fill("#fakt-text", "Unser Stundensatz wird noch festgelegt");
    await page.click("#fakt-form button[type=submit]");
    await page.waitForSelector("#fakten-liste :text('Stundensatz wird noch festgelegt')");
    pruefe(true, "neuer Eintrag wurde gemerkt");
    await page.selectOption("#fakt-art", "kontakt");
    await page.fill("#fakt-text", "Hausverwaltung Test GmbH, Köln, sucht Treppenhausreinigung");
    await page.click("#fakt-form button[type=submit]");
    await page.waitForSelector("#fakten-liste h3:text-is('Kontakte (1)')");
    pruefe((await page.locator("#fakten-liste").textContent()).includes("Hausverwaltung Test GmbH"), "Kontakt wird als eigene Gruppe „Kontakte“ gemerkt");
    await page.fill("#todo-titel", "Angebot für Familie Berger schreiben");
    await page.click("#todo-form button[type=submit]");
    await page.waitForSelector("#todo-liste :text('Familie Berger')");
    await page.click("#todo-liste input[type=checkbox]");
    await page.waitForSelector("#todo-liste .zeile.erledigt");
    pruefe(true, "Aufgabe angelegt und abgehakt");
    await page.fill("#erinnerung-text", "Handelsregister-Auszug prüfen");
    await page.fill("#erinnerung-faellig", "2030-01-02T09:00");
    await page.click("#erinnerung-form button[type=submit]");
    await page.waitForSelector("#erinnerung-liste :text('Handelsregister-Auszug')");
    pruefe(true, "Erinnerung angelegt");
    await page.fill("#suche", "Stundensatz");
    await page.waitForSelector("#suche-treffer .zeile");
    pruefe((await page.locator("#suche-treffer").textContent()).includes("Stundensatz"), "Suche findet den Eintrag");
    await page.getByRole("button", { name: "Bearbeiten" }).first().click();
    await page.waitForSelector("#fakten-liste textarea");
    pruefe(true, "Bearbeiten öffnet den Editor");
    await page.getByRole("button", { name: "Abbrechen" }).first().click();
    await pause(300);
    await foto(page, "05-wissen.png");

    console.log("System");
    await page.click("#reiter-system");
    await page.waitForSelector("#s-werkzeuge .zeile");
    pruefe((await page.locator("#s-anbieter").textContent()).includes("Claude-Abo"), "Anmeldung über das Abo wird angezeigt");
    pruefe((await page.locator("#s-stimme").textContent()).includes("Markus (Premium)"), "beste deutsche Stimme wird angezeigt");
    await page.locator("#s-werkzeuge .zeile:has-text('datei_loeschen') .regler").click();
    await page.waitForFunction(async () => (await (await fetch("/api/zustand")).json()).system.werkzeuge.find((w) => w.name === "datei_loeschen").gesperrt);
    pruefe(true, "Werkzeug lässt sich sperren (Server bestätigt)");
    await page.locator("#s-werkzeuge .zeile:has-text('datei_loeschen') .regler").click();
    await page.waitForFunction(async () => !(await (await fetch("/api/zustand")).json()).system.werkzeuge.find((w) => w.name === "datei_loeschen").gesperrt);
    await page.waitForSelector("#audit-liste :text('werkzeug_gesperrt')", { timeout: 10000 });
    pruefe(true, "Audit zeigt das Sperren des Werkzeugs");
    pruefe((await page.locator("#s-werkzeuge .zeile:has-text('datei_loeschen')").textContent()).includes("erlaubt"), "Schalter zeigt nach dem Zurückstellen wieder „erlaubt“");
    await pause(300);
    await foto(page, "06-system.png");

    console.log("Notstopp");
    await page.click("#reiter-jarvis");
    await page.click("#notstopp");
    await page.waitForSelector("#sperre:not([hidden])");
    pruefe((await page.locator("#kern-zustand").textContent()) === "notstopp", "Kern zeigt Notstopp");
    await page.fill("#text", "Hallo?");
    await page.press("#text", "Enter");
    await page.waitForSelector("#toast.fehler");
    pruefe(true, "Anfrage im Notstopp wird abgewiesen");
    await foto(page, "07-notstopp.png");
    await page.click("#entsperren");
    await page.waitForSelector("#sperre", { state: "hidden" });
    pruefe(true, "Entsperren hebt den Notstopp auf");

    console.log("Sprache (simulierte Spracherkennung)");
    await page.click("#reiter-jarvis");
    const nutzerAnzahl = () => page.locator(".nachricht.nutzer").count();
    await page.click("label:has(#hey-jarvis) .regler");
    await page.waitForFunction(() => document.querySelector("#kern-zustand").textContent === "hört zu");
    pruefe((await page.locator("#kern-detail").textContent()).includes("Hey Jarvis"), "Dauerhören: Kern zeigt „hört zu“ und nennt das Weckwort");
    const vorher = await nutzerAnzahl();
    await page.evaluate(() => window.__hoere("Das ist ein Gespräch ohne das Weckwort", true));
    await pause(700);
    pruefe((await nutzerAnzahl()) === vorher, "ohne Weckwort wird nichts gesendet");
    await page.evaluate(() => window.__hoere("Hey Jarvis, was kannst du für mich tun", true));
    await page.waitForSelector(".nachricht.nutzer .blase:text-is('was kannst du für mich tun')", { timeout: 15000 });
    pruefe(true, "„Hey Jarvis, …“ sendet den Rest des Satzes");
    await page.waitForFunction((n) => document.querySelectorAll(".nachricht.jarvis:not(.denkt)").length >= n, 3, { timeout: 15000 });
    await page.evaluate(() => window.__hoere("Jarvis", true));
    await page.waitForFunction(() => document.querySelector("#sprach-hinweis").textContent.includes("Ich höre"));
    await page.evaluate(() => window.__hoere("Sag mir bitte etwas Nettes", true));
    await page.waitForSelector(".nachricht.nutzer .blase:text-is('Sag mir bitte etwas Nettes')", { timeout: 15000 });
    pruefe(true, "nur das Weckwort: die nächste Aussage wird als Befehl gesendet");
    await page.waitForFunction(() => !document.querySelector(".nachricht.denkt"), null, { timeout: 15000 });
    await page.click("label:has(#hey-jarvis) .regler");
    await page.waitForFunction(() => document.querySelector("#kern-zustand").textContent === "bereit");
    pruefe(true, "Ausschalten beendet das Zuhören");
    await page.click("#mikro");
    await page.waitForFunction(() => document.querySelector("#mikro").getAttribute("aria-pressed") === "true");
    await page.evaluate(() => window.__hoere("Einmal laut gedacht", true));
    await page.waitForSelector(".nachricht.nutzer .blase:text-is('Einmal laut gedacht')", { timeout: 15000 });
    await page.waitForFunction(() => document.querySelector("#mikro").getAttribute("aria-pressed") === "false");
    pruefe(true, "Mikrofon-Taste: einmal zuhören, senden, wieder aus");
    await page.waitForFunction(() => !document.querySelector(".nachricht.denkt"), null, { timeout: 15000 });
    await page.click("#mikro");
    await page.waitForFunction(() => document.querySelector("#mikro").getAttribute("aria-pressed") === "true");
    await page.evaluate(() => window.__erkenner.onerror({ error: "not-allowed" }));
    await page.waitForFunction(() => document.querySelector("#sprach-hinweis").textContent.includes("Mikrofon"));
    pruefe(!(await page.locator("#hey-jarvis").isChecked()), "verweigertes Mikrofon: verständlicher Hinweis, nichts bleibt hängen");
    await foto(page, "07b-sprache.png");

    console.log("Bereich Privat");
    await page.getByRole("button", { name: "Privat", exact: true }).click();
    await page.waitForFunction(() => document.body.dataset.bereich === "privat");
    pruefe(await page.locator("#privat-hinweis").isVisible(), "Hinweis „Privater Bereich“ wird gezeigt");
    pruefe((await page.locator("#chat").textContent()).includes("Noch keine Nachrichten"), "privates Gespräch ist getrennt (leer)");
    await page.click("#reiter-wissen");
    await page.waitForSelector("#fakten-liste .zeile");
    pruefe((await page.locator("#fakten-liste").textContent()).includes("500.000"), "private Ziele sind im privaten Bereich sichtbar");
    pruefe(!(await page.locator("#fakten-liste").textContent()).includes("Familienbetrieb"), "Geschäftswissen ist im privaten Bereich ausgeblendet");
    await foto(page, "08-privat.png");
    await page.getByRole("button", { name: "Geschäft", exact: true }).click();

    console.log("Handy-Ansicht");
    const handy = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "de-DE", timezoneId: "Europe/Berlin" });
    await handy.addCookies([{ name: "jv_token", value: info.token, url: basis }]);
    const hp = await handy.newPage();
    hp.on("console", (m) => { if (["error", "warning"].includes(m.type())) meldungen.push("handy " + m.type() + ": " + m.text()); });
    hp.on("pageerror", (e) => meldungen.push("handy pageerror: " + e.message));
    await hp.goto(basis + "/");
    await hp.waitForSelector("#chat .nachricht");
    for (const id of ["jarvis", "leitstand", "auftraege", "wissen", "system"]) {
      await hp.click("#reiter-" + id);
      await pause(350);
      const breit = await hp.evaluate(() => ({ s: document.documentElement.scrollWidth, w: window.innerWidth }));
      pruefe(breit.s <= breit.w + 1, "Handy: " + id + " ohne seitliches Scrollen (" + breit.s + " ≤ " + breit.w + ")");
      await foto(hp, "handy-" + id + ".png");
    }
    const nav = await hp.locator("#reiter").boundingBox();
    pruefe(nav.y > 700, "Handy: Reiter liegen unten (y=" + Math.round(nav.y) + ")");
    await handy.close();

    pruefe(meldungen.length === 0, "keine Fehler oder Warnungen in der Browser-Konsole" + (meldungen.length ? ": " + meldungen.join(" | ") : ""));
  } catch (e) {
    fehler.push("Abbruch: " + e.message);
    console.log("ABBRUCH: " + e.stack);
  } finally {
    await browser.close();
    kind.removeAllListeners("exit");
    kind.kill("SIGTERM");
  }
  console.log("\nBildschirmfotos: " + OUT);
  console.log(fehler.length ? fehler.length + " Fehler:\n- " + fehler.join("\n- ") : "Alle Oberflächenprüfungen bestanden.");
  process.exit(fehler.length ? 1 : 0);
})();
