--!strict
--[[
	Profile
	Form und Standardwerte eines Spielerprofils.

	Jede Aenderung an diesem Template muss abwaertskompatibel sein: alte
	Speicherstaende werden beim Laden mit Util.reconcile aufgefuellt, nie
	migriert-und-ueberschrieben. Ein Feld umbenennen heisst deshalb: neues
	Feld anlegen, altes eine Version lang mitschleppen, dann entfernen.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local Util = require(ReplicatedStorage.Shared.Util)

export type OwnedVehicle = {
	model: string, -- Schluessel aus Config.Vehicles.Catalog
	plate: string,
	purchasedAt: number,
}

export type Stats = {
	jobsCompleted: number,
	jobsFailed: number,
	arrests: number,
	deaths: number,
	totalEarned: number,
	metersDriven: number,
	highestWanted: number,
}

export type Data = {
	schemaVersion: number,
	cash: number,
	bank: number,
	vehicles: { OwnedVehicle },
	stats: Stats,
	flags: { [string]: boolean },
	lastSeen: number,
}

local Profile = {}

Profile.SCHEMA_VERSION = 3

local TEMPLATE: Data = {
	schemaVersion = Profile.SCHEMA_VERSION,
	cash = Config.Economy.StartingCash,
	bank = Config.Economy.StartingBank,
	vehicles = {},
	stats = {
		jobsCompleted = 0,
		jobsFailed = 0,
		arrests = 0,
		deaths = 0,
		totalEarned = 0,
		metersDriven = 0,
		highestWanted = 0,
	},
	flags = {},
	lastSeen = 0,
}

function Profile.template(): Data
	return Util.deepCopy(TEMPLATE)
end

--[[
	Bringt einen geladenen Speicherstand auf die aktuelle Form.

	Gibt zusaetzlich zurueck, ob etwas repariert werden musste - der
	Aufrufer loggt das, weil haeufige Reparaturen auf einen kaputten
	Schreibpfad hindeuten und nicht auf alte Speicherstaende.
]]
function Profile.reconcile(raw: any): (Data, boolean)
	local repaired = false

	if type(raw) ~= "table" then
		return Profile.template(), true
	end

	local data = raw :: Data

	-- Zahlenfelder gegen Muell absichern. Ein einziges NaN im Geldfeld
	-- macht ein Profil sonst dauerhaft unbrauchbar, weil jeder Vergleich
	-- danach false ergibt.
	if not Util.isFiniteNumber(data.cash) then
		data.cash = TEMPLATE.cash
		repaired = true
	end
	if not Util.isFiniteNumber(data.bank) then
		data.bank = TEMPLATE.bank
		repaired = true
	end

	data.cash = Util.clampInt(data.cash, 0, Config.Economy.MaxCash)
	data.bank = Util.clampInt(data.bank, 0, Config.Economy.MaxCash)

	if type(data.vehicles) ~= "table" then
		data.vehicles = {}
		repaired = true
	else
		-- Unbekannte Modelle aus dem Fuhrpark werfen: ein aus dem Katalog
		-- entferntes Fahrzeug darf den Spawn-Pfad nicht zum Absturz bringen.
		for index = #data.vehicles, 1, -1 do
			local entry = data.vehicles[index]
			if type(entry) ~= "table" or not Config.Vehicles.Catalog[entry.model] then
				table.remove(data.vehicles, index)
				repaired = true
			end
		end
	end

	-- Untertabellen, die keine Tabellen mehr sind, ersetzen. reconcile
	-- fuellt nur fehlende Schluessel auf; eine Zahl an der Stelle von
	-- stats ueberlebt es und laesst erst viel spaeter etwas platzen -
	-- beim ersten data.stats.deaths += 1, weit weg vom Ladepfad.
	for _, field in { "stats", "flags" } do
		if type((data :: any)[field]) ~= "table" then
			(data :: any)[field] = Util.deepCopy((TEMPLATE :: any)[field])
			repaired = true
		end
	end

	Util.reconcile(data :: any, TEMPLATE :: any)
	data.schemaVersion = Profile.SCHEMA_VERSION

	return data, repaired
end

return Profile
