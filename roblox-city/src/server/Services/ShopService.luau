--!strict
--[[
	ShopService
	Kaufvorgaenge.

	Der Client schickt nur einen Katalogschluessel. Preis, Deckung und
	Besitzgrenze kommen ausschliesslich vom Server. Ein Kaufremote, das
	einen Preis entgegennimmt, ist ein Geldautomat fuer Exploiter - deshalb
	steht der Preis nirgends im Argument.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)

local DataService = require(script.Parent.Parent.Data.DataService)
local EconomyService = require(script.Parent.EconomyService)

local ShopService = {}

local function makePlate(): string
	local letters = ""
	for _ = 1, 3 do
		letters ..= string.char(math.random(65, 90))
	end
	return `{letters}-{math.random(100, 999)}`
end

local function purchaseVehicle(player: Player, modelKey: string): (boolean, any)
	local spec = Config.Vehicles.Catalog[modelKey]
	if not spec then
		return false, "Unbekanntes Fahrzeug"
	end

	-- Preis -1 heisst: steht im Katalog, ist aber nicht kaeuflich
	-- (Streifenwagen). Ohne diese Pruefung koennte man sich fuer negatives
	-- Geld einen Polizeiwagen kaufen und dabei noch Guthaben gutschreiben.
	if spec.Price <= 0 then
		return false, "Dieses Fahrzeug steht nicht zum Verkauf"
	end

	local data = DataService.get(player)
	if not data then
		return false, "Profil nicht geladen"
	end

	if #data.vehicles >= Config.Vehicles.MaxOwnedPerPlayer then
		return false, `Fuhrpark voll (maximal {Config.Vehicles.MaxOwnedPerPlayer})`
	end

	for _, entry in data.vehicles do
		if entry.model == modelKey then
			return false, "Besitzt du bereits"
		end
	end

	local result = EconomyService.debit(player, spec.Price, `shop:vehicle:{modelKey}`)
	if not result.ok then
		return false, result.reason or "Kauf fehlgeschlagen"
	end

	table.insert(data.vehicles, {
		model = modelKey,
		plate = makePlate(),
		purchasedAt = os.time(),
	})

	-- Sofort schreiben. Bei einem Serverabsturz zwischen Abbuchung und
	-- naechstem Autosave waere sonst das Geld weg und das Auto nicht da -
	-- der Fehler, den Spieler zu Recht nie verzeihen.
	DataService.flush(player)

	Net.event("Notify"):FireClient(player, `{spec.DisplayName} gekauft fuer {Util.formatMoney(spec.Price)}`, "success")
	ShopService.syncGarage(player)

	return true, {
		model = modelKey,
		cash = result.cash,
		vehicles = data.vehicles,
	}
end

--[[
	Schickt dem Client den Fuhrpark. Nur zur Anzeige - die Berechtigung
	zum Einsetzen prueft VehicleService unabhaengig davon erneut.
]]
function ShopService.syncGarage(player: Player)
	local data = DataService.get(player)
	if not data then
		return
	end

	local catalogue = {}
	for key, spec in Config.Vehicles.Catalog do
		if spec.Price > 0 then
			table.insert(catalogue, {
				model = key,
				displayName = spec.DisplayName,
				price = spec.Price,
				topSpeed = spec.TopSpeed,
				seats = spec.Seats,
			})
		end
	end

	table.sort(catalogue, function(a, b)
		return a.price < b.price
	end)

	Net.event("GarageSync"):FireClient(player, data.vehicles, catalogue)
end

local function requestPurchase(player: Player, category: any, key: any): (boolean, any)
	if type(category) ~= "string" or type(key) ~= "string" then
		return false, "Ungueltige Anfrage"
	end

	if category == "vehicle" then
		return purchaseVehicle(player, key)
	end

	return false, "Unbekannte Kategorie"
end

function ShopService.init()
	Net.bindFunction("RequestPurchase", requestPurchase)
end

function ShopService.start() end

return ShopService
