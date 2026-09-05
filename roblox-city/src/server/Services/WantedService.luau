--!strict
--[[
	WantedService
	Fahndungslevel als Punktekonto statt als Sternenzaehler.

	Punkte statt Sterne, weil sich damit Vergehen unterschiedlich schwer
	gewichten lassen und der Verfall stufenlos laeuft. Der Spieler sieht nur
	die Sterne (Punkte / 100), das Konto bleibt intern.

	Der Verfall haelt an, solange ein Polizist Sichtkontakt hat. Deshalb
	fuehlt sich Verstecken richtig an: nicht "warte den Timer ab", sondern
	"brich den Sichtkontakt ab, dann laeuft der Timer".
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)
local Signal = require(ReplicatedStorage.Shared.Signal)

local DataService = require(script.Parent.Parent.Data.DataService)

type State = {
	points: number,
	stars: number,
	-- os.clock() des letzten Sichtkontakts durch die Polizei.
	lastSeen: number,
}

local WantedService = {}

-- (player, stars, previousStars)
WantedService.StarsChanged = Signal.new()

local states: { [number]: State } = {}

local function stateFor(player: Player): State
	local state = states[player.UserId]
	if not state then
		state = { points = 0, stars = 0, lastSeen = 0 }
		states[player.UserId] = state
	end
	return state
end

local function starsFromPoints(points: number): number
	return math.clamp(math.floor(points / Config.Wanted.PointsPerStar), 0, Config.Wanted.MaxStars)
end

local function apply(player: Player, state: State, reason: string)
	local previous = state.stars
	local stars = starsFromPoints(state.points)

	if stars == previous then
		return
	end

	state.stars = stars
	Net.event("WantedChanged"):FireClient(player, stars, reason)
	WantedService.StarsChanged:Fire(player, stars, previous)

	local data = DataService.get(player)
	if data and stars > data.stats.highestWanted then
		data.stats.highestWanted = stars
	end
end

-- ============================================================
-- Oeffentliche API
-- ============================================================

function WantedService.getStars(player: Player): number
	local state = states[player.UserId]
	return if state then state.stars else 0
end

function WantedService.getPoints(player: Player): number
	local state = states[player.UserId]
	return if state then state.points else 0
end

--[[ Fuegt Punkte hinzu und deckelt auf das Maximum. ]]
function WantedService.addPoints(player: Player, points: number, reason: string)
	if points <= 0 then
		return
	end

	local state = stateFor(player)
	local ceiling = Config.Wanted.MaxStars * Config.Wanted.PointsPerStar + (Config.Wanted.PointsPerStar - 1)

	state.points = math.min(state.points + points, ceiling)
	-- Ein frisches Vergehen setzt den Verfall zurueck, auch ohne Sichtkontakt.
	state.lastSeen = os.clock()

	apply(player, state, reason)
end

--[[ Bequemer Weg ueber den benannten Katalog in der Config. ]]
function WantedService.addOffence(player: Player, offence: string)
	local points = Config.Wanted.Offences[offence]
	if not points then
		warn(`[Wanted] Unbekanntes Vergehen "{offence}"`)
		return
	end
	WantedService.addPoints(player, points, offence)
end

--[[ Setzt mindestens dieses Sternenlevel. Fuer Jobs, die per Definition
     mit einem Fahndungslevel starten. ]]
function WantedService.setMinimumStars(player: Player, stars: number, reason: string)
	local target = math.clamp(stars, 0, Config.Wanted.MaxStars) * Config.Wanted.PointsPerStar
	local state = stateFor(player)

	if state.points >= target then
		return
	end

	state.points = target
	state.lastSeen = os.clock()
	apply(player, state, reason)
end

function WantedService.clear(player: Player, reason: string)
	local state = stateFor(player)
	state.points = 0
	state.lastSeen = 0
	apply(player, state, reason)
end

--[[ Von PoliceService aufgerufen, solange ein Beamter Sichtkontakt hat. ]]
function WantedService.markSeen(player: Player)
	local state = states[player.UserId]
	if state then
		state.lastSeen = os.clock()
	end
end

--[[ Sichtweite der Polizei beim aktuellen Level. ]]
function WantedService.sightRange(player: Player): number
	local stars = WantedService.getStars(player)
	if stars <= 0 then
		return 0
	end
	return Config.Wanted.CopSightRange[math.min(stars, #Config.Wanted.CopSightRange)]
end

--[[ Wie viele Beamte das aktuelle Level jagen sollen. ]]
function WantedService.desiredCopCount(player: Player): number
	local stars = WantedService.getStars(player)
	if stars <= 0 then
		return 0
	end
	return Config.Wanted.CopsPerStar[math.min(stars, #Config.Wanted.CopsPerStar)]
end

-- ============================================================
-- Start
-- ============================================================

function WantedService.init() end

function WantedService.start()
	Players.PlayerRemoving:Connect(function(player)
		states[player.UserId] = nil
	end)

	Players.PlayerAdded:Connect(function(player)
		stateFor(player)
		player.CharacterAdded:Connect(function()
			-- Nach dem Tod bleibt das Level bestehen, faellt aber deutlich:
			-- Ein Totalreset macht Sterben zur billigsten Fluchtstrategie.
			local state = stateFor(player)
			if state.points > 0 then
				state.points = math.floor(state.points * 0.5)
				state.lastSeen = os.clock()
				apply(player, state, "death")
			end
		end)
	end)

	-- Verfall. Ein Durchlauf pro Sekunde reicht: das Level ist eine
	-- langsame Groesse und ein Heartbeat-Tick pro Frame waere reine
	-- Rechenzeit fuer nichts.
	task.spawn(function()
		while true do
			local elapsed = task.wait(1)

			for userId, state in states do
				if state.points <= 0 then
					continue
				end

				local player = Players:GetPlayerByUserId(userId)
				if not player then
					continue
				end

				local sinceSeen = os.clock() - state.lastSeen
				if sinceSeen < Config.Wanted.LineOfSightGrace then
					continue
				end

				local index = math.clamp(state.stars, 1, #Config.Wanted.DecaySeconds)
				local perSecond = Config.Wanted.PointsPerStar / Config.Wanted.DecaySeconds[index]

				state.points = math.max(0, state.points - perSecond * elapsed)
				apply(player, state, "decay")
			end
		end
	end)
end

return WantedService
