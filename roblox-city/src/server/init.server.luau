--!strict
--[[
	Serverstart.

	Zwei Phasen, und die Reihenfolge ist kein Zufall:

	  init()   Remotes anlegen, Ordner erzeugen, Handler binden. Nichts
	           darf hier yielden, damit ein Spieler, der in der ersten
	           Sekunde joint, keine halb fertige Welt vorfindet.
	  start()  Schleifen und Ereignisse. Ab hier laeuft das Spiel.

	Die Abhaengigkeiten werden hier von Hand verdrahtet statt ueber eine
	Service-Registry aufgeloest. Bei acht Services ist eine Registry
	Selbstzweck: sie versteckt genau die Reihenfolge, die man beim
	Fehlersuchen wissen will.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)

local DataService = require(script.Data.DataService)
local AntiCheatService = require(script.Services.AntiCheatService)
local EconomyService = require(script.Services.EconomyService)
local JobService = require(script.Services.JobService)
local PoliceService = require(script.Services.PoliceService)
local ShopService = require(script.Services.ShopService)
local VehicleService = require(script.Services.VehicleService)
local WantedService = require(script.Services.WantedService)
local WorldService = require(script.Services.WorldService)

-- Reihenfolge: Welt vor allem, was Boden braucht. Daten vor allem, was
-- Daten liest. Anti-Cheat zuletzt, damit es die anderen kennt.
local SERVICES = {
	{ name = "World", module = WorldService },
	{ name = "Data", module = DataService },
	{ name = "Economy", module = EconomyService },
	{ name = "Wanted", module = WantedService },
	{ name = "Vehicle", module = VehicleService },
	{ name = "Police", module = PoliceService },
	{ name = "Job", module = JobService },
	{ name = "Shop", module = ShopService },
	{ name = "AntiCheat", module = AntiCheatService },
}

local startedAt = os.clock()

Net.publish()

for _, entry in SERVICES do
	local ok, err = pcall(entry.module.init)
	if not ok then
		-- Weiterlaufen statt abbrechen: ein kaputter Shop soll nicht
		-- verhindern, dass die Wirtschaft laedt.
		warn(`[Boot] init von {entry.name} gescheitert: {err}`)
	end
end

for _, entry in SERVICES do
	local ok, err = pcall(entry.module.start)
	if not ok then
		warn(`[Boot] start von {entry.name} gescheitert: {err}`)
	end
end

-- ============================================================
-- Verdrahtung zwischen Services
-- ============================================================

-- Fuhrpark an den Client, sobald das Profil steht.
DataService.ProfileLoaded:Connect(function(player: Player)
	ShopService.syncGarage(player)
end)

--[[
	Tod kostet Bargeld. Absichtlich hier und nicht in EconomyService:
	die Regel gehoert zum Spiel, nicht zur Buchhaltung, und beim
	Ausbalancieren sucht man sie an genau dieser Stelle.
]]
local function watchCharacter(player: Player)
	player.CharacterAdded:Connect(function(character)
		local humanoid = character:WaitForChild("Humanoid", 10)
		if not humanoid or not humanoid:IsA("Humanoid") then
			return
		end

		humanoid.Died:Connect(function()
			local data = DataService.get(player)
			if data then
				data.stats.deaths += 1
			end

			local lost = EconomyService.forfeit(player, Config.Economy.CashLossOnDeath, "death")
			if lost > 0 then
				Net.event("Notify"):FireClient(player, `Beim Aufwachen fehlen dir {lost}.`, "error")
			end

			-- Der Respawn versetzt den Charakter. Ohne diese Pause meldet
			-- die Bewegungspruefung den eigenen Respawn als Teleport.
			AntiCheatService.excuse(player, 6)
		end)
	end)
end

Players.PlayerAdded:Connect(watchCharacter)
for _, player in Players:GetPlayers() do
	watchCharacter(player)
end

-- Streifenwagen als Beute in der Stadt verteilen, damit Fahrzeugdiebstahl
-- ohne gebaute Karte ueberhaupt ausprobiert werden kann.
task.defer(function()
	for index = 1, 4 do
		local angle = (index / 4) * math.pi * 2
		local position = Vector3.new(math.cos(angle) * 90, 6, math.sin(angle) * 90)
		VehicleService.spawn("PoliceCruiser", CFrame.new(position), 0)
	end
end)

print(string.format("[Boot] LibertyCity bereit in %.0f ms", (os.clock() - startedAt) * 1000))
