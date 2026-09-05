--!strict
--[[
	JobService
	Auftraege als Geldquelle - und damit der Pfad, an dem ein Wirtschafts-
	system als erstes ausgenutzt wird.

	Drei Regeln, die das verhindern:

	1. Der Server entscheidet, wann ein Auftrag erfuellt ist. Es gibt kein
	   Remote namens "JobCompleted". Der Client kann einen Abschluss nicht
	   melden, nur erleben.
	2. Jeder Auftrag traegt einen Idempotenzschluessel aus Spieler, Typ und
	   Startzeitpunkt. Selbst wenn der Abschlusspfad doppelt laeuft, zahlt
	   die Wirtschaft einmal.
	3. Ein Spieler hat hoechstens einen aktiven Auftrag. Ohne das startet
	   man zwanzig Lieferungen gleichzeitig und faehrt sie mit einer
	   einzigen Fahrt ab.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)
local Util = require(ReplicatedStorage.Shared.Util)

local DataService = require(script.Parent.Parent.Data.DataService)
local EconomyService = require(script.Parent.EconomyService)
local WantedService = require(script.Parent.WantedService)

type Active = {
	key: string,
	startedAt: number,
	deadline: number,
	destination: Vector3,
	marker: BasePart?,
	-- Fuer Auftraege, die Verweildauer verlangen.
	holdProgress: number,
	holdRequired: number,
	idempotencyKey: string,
}

local JobService = {}

local active: { [number]: Active } = {}
local lastFinished: { [number]: { [string]: number } } = {}
local markerFolder: Folder

local ARRIVAL_RADIUS = 14
local TICK = 0.5

-- ============================================================
-- Intern
-- ============================================================

local function groundNear(origin: Vector3, minDistance: number, maxDistance: number): Vector3?
	for _ = 1, 8 do
		local angle = math.random() * math.pi * 2
		local distance = minDistance + math.random() * (maxDistance - minDistance)
		local candidate = origin + Vector3.new(math.cos(angle) * distance, 0, math.sin(angle) * distance)

		local params = RaycastParams.new()
		params.FilterType = Enum.RaycastFilterType.Exclude
		params.FilterDescendantsInstances = { markerFolder }

		local result = Workspace:Raycast(candidate + Vector3.new(0, 150, 0), Vector3.new(0, -400, 0), params)
		if result then
			return result.Position + Vector3.new(0, 1, 0)
		end
	end
	return nil
end

local function makeMarker(position: Vector3, colour: Color3): BasePart
	local marker = Instance.new("Part")
	marker.Name = "JobMarker"
	marker.Anchored = true
	marker.CanCollide = false
	marker.Size = Vector3.new(ARRIVAL_RADIUS, 0.4, ARRIVAL_RADIUS)
	marker.Shape = Enum.PartType.Cylinder
	-- Zylinder liegen in Roblox auf der Seite; einmal kippen, damit daraus
	-- ein Bodenring wird statt einer stehenden Scheibe.
	marker.CFrame = CFrame.new(position) * CFrame.Angles(0, 0, math.pi / 2)
	marker.Color = colour
	marker.Material = Enum.Material.Neon
	marker.Transparency = 0.4
	marker.Parent = markerFolder
	return marker
end

local function clearActive(userId: number)
	local job = active[userId]
	if not job then
		return
	end

	if job.marker then
		job.marker:Destroy()
	end
	active[userId] = nil
end

local function finish(player: Player, job: Active, success: boolean, reason: string)
	local data = DataService.get(player)

	if success then
		local spec = Config.Jobs.Definitions[job.key]
		local remaining = math.max(0, job.deadline - os.clock())

		local payout = spec.BasePayout
		if spec.TimeBonusPerSecond then
			payout += remaining * spec.TimeBonusPerSecond
		end

		payout = Util.clampInt(payout, 1, Config.Economy.MaxSingleTransaction)

		local result = EconomyService.credit(player, payout, `job:{job.key}`, job.idempotencyKey)
		if data then
			data.stats.jobsCompleted += 1
		end

		if result.ok then
			Net.event("Notify"):FireClient(player, `{spec.DisplayName} erledigt: {Util.formatMoney(payout)}`, "success")
		end
	else
		if data then
			data.stats.jobsFailed += 1
		end
		Net.event("Notify"):FireClient(player, `Auftrag gescheitert: {reason}`, "error")
	end

	local finishedMap = lastFinished[player.UserId]
	if not finishedMap then
		finishedMap = {}
		lastFinished[player.UserId] = finishedMap
	end
	finishedMap[job.key] = os.clock()

	clearActive(player.UserId)
	Net.event("JobStateChanged"):FireClient(player, nil)
end

-- ============================================================
-- Ablauf
-- ============================================================

local function tickJob(player: Player, job: Active, deltaTime: number)
	local character = player.Character
	local root = character and character:FindFirstChild("HumanoidRootPart") :: BasePart?

	if not root then
		return
	end

	if os.clock() > job.deadline then
		finish(player, job, false, "Zeit abgelaufen")
		return
	end

	local spec = Config.Jobs[job.key]
	local distance = (root.Position - job.destination).Magnitude
	local inZone = distance <= ARRIVAL_RADIUS

	if job.holdRequired > 0 then
		if inZone then
			job.holdProgress += deltaTime
			if job.marker then
				job.marker.Transparency = 0.4 - 0.3 * math.clamp(job.holdProgress / job.holdRequired, 0, 1)
			end

			Net.event("JobProgress"):FireClient(player, job.holdProgress / job.holdRequired, math.max(0, job.deadline - os.clock()))

			if job.holdProgress >= job.holdRequired then
				finish(player, job, true, "")
			end
		else
			-- Zurueckfallen statt zuruecksetzen: kurz aus der Zone
			-- gedraengt zu werden soll nicht alles zunichte machen.
			job.holdProgress = math.max(0, job.holdProgress - deltaTime * 0.5)
			Net.event("JobProgress"):FireClient(player, job.holdProgress / job.holdRequired, math.max(0, job.deadline - os.clock()))
		end
		return
	end

	-- RequiresVehicle erzwingt nichts: zu Fuss ist erlaubt, nur langsam,
	-- und der Zeitbonus bestraft das von allein. Die Angabe dient der
	-- Anzeige im Auftragsmenue.
	Net.event("JobProgress"):FireClient(player, 1 - math.clamp(distance / 400, 0, 1), math.max(0, job.deadline - os.clock()))

	if inZone then
		finish(player, job, true, "")
	end
end

-- ============================================================
-- Remote-Handler
-- ============================================================

local function requestStartJob(player: Player, jobKey: any): (boolean, any)
	if type(jobKey) ~= "string" then
		return false, "Ungueltiger Auftrag"
	end

	local spec = Config.Jobs.Definitions[jobKey]
	if not spec then
		return false, "Unbekannter Auftrag"
	end

	if active[player.UserId] then
		return false, "Du hast bereits einen laufenden Auftrag"
	end

	local finishedMap = lastFinished[player.UserId]
	if finishedMap and finishedMap[jobKey] then
		local waited = os.clock() - finishedMap[jobKey]
		if waited < Config.Jobs.CooldownSeconds then
			return false, `Noch {math.ceil(Config.Jobs.CooldownSeconds - waited)} Sekunden Pause`
		end
	end

	local character = player.Character
	local root = character and character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not root then
		return false, "Kein Charakter in der Welt"
	end

	local destination = groundNear(root.Position, 120, 420)
	if not destination then
		return false, "Kein Ziel gefunden"
	end

	local colour = if spec.WantedOnStart > 0 then Color3.fromRGB(235, 76, 76) else Color3.fromRGB(90, 200, 255)

	local job: Active = {
		key = jobKey,
		startedAt = os.clock(),
		deadline = os.clock() + spec.TimeLimitSeconds,
		destination = destination,
		marker = makeMarker(destination, colour),
		holdProgress = 0,
		holdRequired = spec.HoldSeconds or 0,
		-- os.time statt os.clock im Schluessel: os.clock startet pro Server
		-- bei null, waere also ueber Serverwechsel hinweg nicht eindeutig.
		idempotencyKey = `job:{jobKey}:{player.UserId}:{os.time()}:{math.random(1000, 9999)}`,
	}

	active[player.UserId] = job

	if spec.WantedOnStart > 0 then
		WantedService.setMinimumStars(player, spec.WantedOnStart, `job:{jobKey}`)
	end

	Net.event("JobStateChanged"):FireClient(player, {
		key = jobKey,
		displayName = spec.DisplayName,
		description = spec.Description,
		destination = destination,
		timeLimit = spec.TimeLimitSeconds,
		holdRequired = job.holdRequired,
	})

	return true, { destination = destination }
end

local function requestAbortJob(player: Player)
	local job = active[player.UserId]
	if job then
		finish(player, job, false, "abgebrochen")
	end
end

-- ============================================================
-- Start
-- ============================================================

function JobService.init()
	markerFolder = Workspace:FindFirstChild("JobMarkers") :: Folder
	if not markerFolder then
		markerFolder = Instance.new("Folder")
		markerFolder.Name = "JobMarkers"
		markerFolder.Parent = Workspace
	end

	Net.bindFunction("RequestStartJob", requestStartJob)
	Net.bindEvent("RequestAbortJob", requestAbortJob)
end

function JobService.start()
	Players.PlayerRemoving:Connect(function(player)
		clearActive(player.UserId)
		lastFinished[player.UserId] = nil
	end)

	task.spawn(function()
		while true do
			local deltaTime = task.wait(TICK)

			for userId, job in active do
				local player = Players:GetPlayerByUserId(userId)
				if not player then
					clearActive(userId)
					continue
				end

				local ok, err = pcall(tickJob, player, job, deltaTime)
				if not ok then
					warn(`[Jobs] Tick gescheitert fuer {player.Name}: {err}`)
				end
			end
		end
	end)
end

return JobService
