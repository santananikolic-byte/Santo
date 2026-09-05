--!strict
--[[
	Config
	Zentrale Stellschrauben fuer das gesamte Spiel.

	Diese Tabelle wird an den Client repliziert, enthaelt also bewusst KEINE
	Werte, die ein Spieler nicht kennen darf. Alles, was Geheimnis bleiben
	muss (Auszahlungs-Formeln, Anti-Cheat-Schwellen), liegt in
	ServerScriptService und niemals hier.
]]

local Config = {}

-- ============================================================
-- Wirtschaft
-- ============================================================

Config.Economy = {
	-- Startkapital fuer einen frischen Account.
	StartingCash = 500,
	StartingBank = 0,

	-- Obergrenze. Verhindert, dass ein Integer-Overflow oder ein Bug im
	-- Auszahlungspfad einen Account unbrauchbar macht.
	MaxCash = 999_999_999,

	-- Ein einzelner Transfer darf nie groesser sein als das. Jede
	-- Auszahlung, die das reissen wuerde, gilt als Bug und wird geloggt.
	MaxSingleTransaction = 5_000_000,

	-- Anteil des Bargelds, das beim Tod verloren geht. Geld auf der Bank
	-- ist sicher. Das ist der Grund, warum Spieler die Bank benutzen.
	CashLossOnDeath = 0.20,

	-- Bargeld, das die Polizei bei einer Verhaftung einzieht.
	CashLossOnArrest = 0.35,
}

-- ============================================================
-- Fahndungslevel
-- ============================================================

Config.Wanted = {
	MaxStars = 5,

	-- Sekunden ohne Sichtkontakt zur Polizei, bis ein Stern verfaellt.
	-- Hoehere Level brauchen laenger, damit eine 5-Sterne-Jagd sich auch
	-- wie eine anfuehlt.
	DecaySeconds = { 12, 18, 26, 38, 55 },

	-- Solange ein Cop den Spieler sieht, laeuft der Verfall nicht.
	-- Danach dauert es diese Zeit, bis der Timer ueberhaupt anspringt.
	LineOfSightGrace = 4,

	-- Wie viele Cops pro Sternenlevel gleichzeitig jagen.
	CopsPerStar = { 1, 2, 4, 6, 8 },

	-- Sichtweite der Polizei in Studs, pro Sternenlevel.
	CopSightRange = { 90, 120, 150, 190, 240 },

	-- Punkte, die ein Vergehen auf das Fahndungskonto legt. 100 Punkte
	-- entsprechen einem Stern.
	Offences = {
		Speeding = 15,
		HitPedestrian = 40,
		VehicleTheft = 60,
		Assault = 70,
		StoreRobbery = 180,
		KilledCivilian = 200,
		KilledOfficer = 320,
	},

	PointsPerStar = 100,
}

-- ============================================================
-- Fahrzeuge
-- ============================================================

Config.Vehicles = {
	-- Reichweite, in der ein Spieler ein Fahrzeug betreten darf. Der Server
	-- prueft das erneut, der Client benutzt es nur fuer den Prompt.
	InteractDistance = 14,

	-- Fahrzeuge ohne Fahrer werden nach dieser Zeit aufgeraeumt, damit die
	-- Stadt nicht zuparkt.
	AbandonedCleanupSeconds = 180,

	-- Maximale Anzahl gleichzeitig gespawnter Fahrzeuge pro Server.
	MaxActiveVehicles = 60,

	-- Wie viele Fahrzeuge ein einzelner Spieler besitzen darf.
	MaxOwnedPerPlayer = 3,

	Catalog = {
		Compact = {
			DisplayName = "Blista Kompakt",
			Price = 12_000,
			TopSpeed = 78,
			Acceleration = 22,
			HandlingGrip = 0.82,
			Mass = 1400,
			Seats = 4,
			Body = "Car",
			Colour = Color3.fromRGB(214, 84, 58),
			ChassisSize = Vector3.new(6, 2, 11),
		},
		Sedan = {
			DisplayName = "Vapid Stanier",
			Price = 24_000,
			TopSpeed = 92,
			Acceleration = 26,
			HandlingGrip = 0.78,
			Mass = 1750,
			Seats = 4,
			Body = "Car",
			Colour = Color3.fromRGB(58, 92, 156),
			ChassisSize = Vector3.new(6.4, 2.2, 13),
		},
		Sports = {
			DisplayName = "Pegassi Comet",
			Price = 145_000,
			TopSpeed = 148,
			Acceleration = 48,
			HandlingGrip = 0.94,
			Mass = 1250,
			Seats = 2,
			Body = "Car",
			Colour = Color3.fromRGB(236, 190, 62),
			ChassisSize = Vector3.new(6.2, 1.6, 12.5),
		},
		Muscle = {
			DisplayName = "Declasse Vigero",
			Price = 88_000,
			TopSpeed = 126,
			Acceleration = 41,
			HandlingGrip = 0.71,
			Mass = 1680,
			Seats = 2,
			Body = "Car",
			Colour = Color3.fromRGB(38, 38, 44),
			ChassisSize = Vector3.new(6.6, 2, 13.5),
		},
		Motorcycle = {
			DisplayName = "Nagasaki Carbon",
			Price = 62_000,
			TopSpeed = 155,
			Acceleration = 55,
			HandlingGrip = 0.68,
			Mass = 420,
			Seats = 1,
			Body = "Bike",
			Colour = Color3.fromRGB(180, 30, 30),
			ChassisSize = Vector3.new(2, 1.6, 7),
		},
		PoliceCruiser = {
			DisplayName = "Police Cruiser",
			Price = -1, -- nicht kaeuflich
			TopSpeed = 118,
			Acceleration = 38,
			HandlingGrip = 0.88,
			Mass = 1900,
			Seats = 4,
			Body = "Car",
			Colour = Color3.fromRGB(240, 240, 245),
			ChassisSize = Vector3.new(6.4, 2.2, 13),
		},
	},
}

-- ============================================================
-- Jobs
-- ============================================================

Config.Jobs = {
	-- Abstand zwischen zwei Auftraegen desselben Typs.
	CooldownSeconds = 45,
}

-- Die Auftraege stehen bewusst in einer eigenen Tabelle und nicht neben
-- CooldownSeconds: sonst muss jede Schleife ueber die Auftraege wissen,
-- dass ein Eintrag darin gar kein Auftrag ist.
Config.Jobs.Definitions = {
	Delivery = {
		DisplayName = "Lieferung",
		Description = "Bring das Paket ans Ziel, bevor die Zeit ablaeuft.",
		BasePayout = 850,
		-- Bonus pro Sekunde Restzeit.
		TimeBonusPerSecond = 12,
		TimeLimitSeconds = 180,
		RequiresVehicle = true,
		WantedOnStart = 0,
	},

	StoreRobbery = {
		DisplayName = "Ladenueberfall",
		Description = "Halte die Kasse offen, bis der Tresor leer ist.",
		BasePayout = 4_200,
		-- Der Spieler muss so lange im Laden bleiben.
		HoldSeconds = 25,
		TimeLimitSeconds = 300,
		RequiresVehicle = false,
		WantedOnStart = 2,
	},

	Heist = {
		DisplayName = "Bankraub",
		Description = "Vier Minuten. Tresorraum, Beute, Fluchtwagen.",
		BasePayout = 38_000,
		-- Anteil pro zusaetzlichem Teilnehmer, geteilt durch die Crew.
		CrewBonusPerMember = 0.35,
		MinCrewSize = 2,
		MaxCrewSize = 4,
		HoldSeconds = 90,
		TimeLimitSeconds = 240,
		RequiresVehicle = true,
		WantedOnStart = 4,
	},
}

-- ============================================================
-- Persistenz
-- ============================================================

Config.Data = {
	StoreName = "PlayerData_v3",

	-- Ein Schreibvorgang erneuert die Sitzungssperre UND sichert die Daten.
	-- Darum gibt es hier nur eine Kadenz statt getrennter Autosave- und
	-- Heartbeat-Timer: zwei Timer waeren doppelt so viele DataStore-Writes
	-- fuer exakt denselben Effekt.
	SaveIntervalSeconds = 30,

	-- Sperre gegen doppelte Sitzungen. Ohne das kann ein Spieler auf zwei
	-- Servern gleichzeitig laden und Geld duplizieren. Muss deutlich
	-- groesser sein als SaveIntervalSeconds, sonst laeuft die eigene Sperre
	-- zwischen zwei Writes ab.
	SessionLockSeconds = 90,

	-- Wiederholungen bei DataStore-Fehlern, mit exponentiellem Abstand.
	MaxRetries = 5,
	RetryBaseDelay = 1.0,

	-- Zeitbudget beim Serverabbau, um alle Profile zu schreiben.
	ShutdownTimeout = 25,
}

-- ============================================================
-- Netzwerk
-- ============================================================

Config.Net = {
	-- Standardbudget pro Remote, falls kein spezielles gesetzt ist.
	DefaultRateLimit = { calls = 20, window = 1.0 },
}

-- ============================================================
-- Polizei
-- ============================================================

Config.Police = {
	-- Tempo, ab dem ein sichtbarer Fahrer wegen Raserei auffaellt (Studs/s).
	SpeedLimit = 85,

	-- So lange muss er darueber liegen, bevor es Punkte gibt.
	SpeedingGraceSeconds = 3,

	-- Reichweite, in der ein Beamter eine Verhaftung ausloest.
	ArrestDistance = 12,

	-- So lange muss der Beamte in Reichweite bleiben.
	ArrestHoldSeconds = 2.5,

	-- Abstand zwischen zwei Denkschritten der KI. 0.2 statt jedes Frame:
	-- Wegfindung ist teuer und ein Streifenwagen braucht keine 60 Hz.
	ThinkInterval = 0.2,

	-- Wie weit vom Ziel entfernt Beamte einsetzen.
	SpawnDistance = 220,

	NpcWalkSpeed = 20,
	NpcHealth = 120,
}

table.freeze(Config)
return Config
