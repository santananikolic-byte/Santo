--!nocheck
--[[
	Testlauf fuer die Teile, die ohne Roblox pruefbar sind.

		luau tools/spec.luau     (aus dem Projektverzeichnis)

	Bewusst nur die reine Logik: Formatierung, Abgleich von Speicher-
	staenden, Token-Bucket, Signal. Alles, was Instanzen anfasst, gehoert
	in einen Testlauf in Studio - ein Nachbau der Roblox-API waere selbst
	die groesste Fehlerquelle im Projekt.

	Genau diese vier Module tragen aber die Stellen, an denen ein Fehler
	still bleibt: ein falsch abgeglichener Speicherstand faellt erst Tage
	spaeter auf, ein durchlaessiger Token-Bucket nie.
]]

local Util = require("../src/shared/Util")
local Signal = require("../src/shared/Signal")
local RateLimiter = require("../src/shared/RateLimiter")

local passed = 0
local failed = 0
local failures: { string } = {}

local function check(name: string, condition: boolean, detail: string?)
	if condition then
		passed += 1
	else
		failed += 1
		table.insert(failures, `{name}{if detail then `  ({detail})` else ""}`)
	end
end

local function equals(name: string, actual: any, expected: any)
	check(name, actual == expected, `erwartet {tostring(expected)}, bekommen {tostring(actual)}`)
end

-- ============================================================
-- Util.formatMoney
-- ============================================================

equals("formatMoney: null", Util.formatMoney(0), "$0")
equals("formatMoney: dreistellig", Util.formatMoney(999), "$999")
equals("formatMoney: Tausendergrenze", Util.formatMoney(1000), "$1.000")
equals("formatMoney: Millionen", Util.formatMoney(1234567), "$1.234.567")
equals("formatMoney: negativ", Util.formatMoney(-500), "-$500")
-- Nachkommastellen werden abgeschnitten, nicht gerundet: ein Kontostand
-- ist ganzzahlig, und Aufrunden in der Anzeige waere eine Luege.
equals("formatMoney: Nachkomma", Util.formatMoney(1500.9), "$1.500")

-- ============================================================
-- Util.formatClock
-- ============================================================

equals("formatClock: null", Util.formatClock(0), "0:00")
equals("formatClock: unter einer Minute", Util.formatClock(7), "0:07")
equals("formatClock: dreieinhalb Minuten", Util.formatClock(187), "3:07")
equals("formatClock: negativ wird null", Util.formatClock(-5), "0:00")

-- ============================================================
-- Util.clampInt
-- ============================================================

equals("clampInt: rundet auf", Util.clampInt(3.6, 0, 100), 4)
equals("clampInt: rundet ab", Util.clampInt(3.4, 0, 100), 3)
equals("clampInt: deckelt oben", Util.clampInt(500, 0, 100), 100)
equals("clampInt: deckelt unten", Util.clampInt(-20, 0, 100), 0)
-- NaN ist der Wert, der ein Profil dauerhaft zerstoert: jeder Vergleich
-- damit ist false, also greift danach keine einzige Pruefung mehr.
equals("clampInt: NaN faellt auf das Minimum", Util.clampInt(0 / 0, 5, 100), 5)

-- ============================================================
-- Util.isFiniteNumber
-- ============================================================

equals("isFiniteNumber: Zahl", Util.isFiniteNumber(42), true)
equals("isFiniteNumber: NaN", Util.isFiniteNumber(0 / 0), false)
equals("isFiniteNumber: unendlich", Util.isFiniteNumber(math.huge), false)
equals("isFiniteNumber: minus unendlich", Util.isFiniteNumber(-math.huge), false)
equals("isFiniteNumber: Text", Util.isFiniteNumber("100"), false)
equals("isFiniteNumber: nil", Util.isFiniteNumber(nil), false)

-- ============================================================
-- Util.deepCopy
-- ============================================================

do
	local original = { a = 1, nested = { b = 2, list = { 1, 2, 3 } } }
	local copy = Util.deepCopy(original)

	copy.nested.b = 99
	copy.nested.list[1] = 99

	equals("deepCopy: Original bleibt unberuehrt", original.nested.b, 2)
	equals("deepCopy: Listen werden mitkopiert", original.nested.list[1], 1)
	equals("deepCopy: Werte kommen an", copy.a, 1)
end

-- ============================================================
-- Util.reconcile
-- ============================================================

do
	local template = {
		cash = 500,
		stats = { deaths = 0, arrests = 0 },
		flags = {},
	}

	local old = { cash = 12_000, stats = { deaths = 7 } }
	local result = Util.reconcile(old, template)

	-- Der wichtigste Fall ueberhaupt: ein vorhandener Wert darf beim
	-- Nachfuellen niemals durch den Standardwert ersetzt werden. Genau das
	-- waere ein zurueckgesetzter Kontostand nach einem Update.
	equals("reconcile: vorhandener Wert bleibt", result.cash, 12_000)
	equals("reconcile: vorhandener Unterwert bleibt", result.stats.deaths, 7)
	equals("reconcile: fehlender Unterwert kommt dazu", result.stats.arrests, 0)
	check("reconcile: fehlende Tabelle kommt dazu", type(result.flags) == "table")

	-- Und die Vorlage darf dabei nicht mitwandern.
	result.stats.arrests = 42
	equals("reconcile: Vorlage bleibt unberuehrt", template.stats.arrests, 0)
end

-- ============================================================
-- RateLimiter
-- ============================================================

do
	local limiter = RateLimiter.new(3, 1.0)
	local userId = 1

	equals("RateLimiter: erster Aufruf", limiter:Consume(userId), true)
	equals("RateLimiter: zweiter Aufruf", limiter:Consume(userId), true)
	equals("RateLimiter: dritter Aufruf", limiter:Consume(userId), true)
	equals("RateLimiter: vierter Aufruf blockt", limiter:Consume(userId), false)

	-- Zweiter Spieler hat ein eigenes Budget. Ohne das legt ein einzelner
	-- Exploiter das Remote fuer alle anderen lahm.
	equals("RateLimiter: eigenes Budget pro Spieler", limiter:Consume(2), true)

	-- Warten, bis nachgefuellt ist.
	local waitUntil = os.clock() + 0.5
	while os.clock() < waitUntil do end

	equals("RateLimiter: fuellt mit der Zeit nach", limiter:Consume(userId), true)

	limiter:Release(userId)
	equals("RateLimiter: nach Freigabe volles Budget", limiter:Consume(userId), true)
end

-- ============================================================
-- Signal
-- ============================================================

do
	local signal = Signal.new()
	local calls = 0
	local lastValue = nil

	local connection = signal:Connect(function(value)
		calls += 1
		lastValue = value
	end)

	signal:Fire("hallo")
	equals("Signal: Handler laeuft", calls, 1)
	equals("Signal: Argument kommt an", lastValue, "hallo")

	connection:Disconnect()
	signal:Fire("und tschuess")
	equals("Signal: nach Disconnect still", calls, 1)

	local onceCalls = 0
	signal:Once(function()
		onceCalls += 1
	end)
	signal:Fire()
	signal:Fire()
	equals("Signal: Once laeuft genau einmal", onceCalls, 1)

	-- Ein Handler, der sich waehrend des Feuerns abmeldet, darf die
	-- Schleife ueber die uebrigen Handler nicht zerreissen.
	local a, b = 0, 0
	local selfRemoving
	selfRemoving = signal:Connect(function()
		a += 1
		selfRemoving:Disconnect()
	end)
	signal:Connect(function()
		b += 1
	end)

	signal:Fire()
	signal:Fire()
	equals("Signal: Abmeldung im Handler", a, 1)
	equals("Signal: uebrige Handler laufen weiter", b, 2)
end

-- ============================================================
-- Auswertung
-- ============================================================

print(`{passed} bestanden, {failed} fehlgeschlagen`)

if failed > 0 then
	for _, entry in failures do
		print(`  FEHLER  {entry}`)
	end
	error("Testlauf fehlgeschlagen", 0)
end
