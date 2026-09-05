--!strict
--[[
	PoliceService
	Streifen, Verfolgung, Verhaftung.

	Bewusste Grenze des Umfangs: die Polizei schiesst nicht. Sie verfolgt,
	stellt und verhaftet. Ein Waffensystem waere ein eigenes Projekt mit
	eigenem Anti-Cheat (Trefferpruefung, Feuerrate, Reichweite), und ein
	halbfertiges Waffensystem ist schlimmer als keines. Die Verhaftung
	erledigt denselben Zweck: sie kostet Geld und beendet die Jagd.

	Die KI denkt fuenfmal pro Sekunde, nicht jeden Frame. Wegfindung ist
	die teuerste Einzeloperation in diesem Projekt, und ein Streifenwagen,
	der seine Route 60-mal pro Sekunde neu berechnet, kostet mehr Leistung
	als das gesamte restliche Spiel.
]]

local PathfindingService = game:GetService("PathfindingService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)

local AntiCheatService = require(script.Parent.AntiCheatService)
local CopFactory = require(script.Parent.CopFactory)
local DataService = require(script.Parent.Parent.Data.DataService)
local EconomyService = require(script.Parent.EconomyService)
local VehicleService = require(script.Parent.VehicleService)
local WantedService = require(script.Parent.WantedService)

type Cop = {
	model: Model,
	humanoid: Humanoid,
	root: BasePart,
	targetUserId: number,
	waypoints: { PathWaypoint },
	waypointIndex: number,
	lastPathAt: number,
	arrestHold: number,
	stuckSince: number,
	lastPosition: Vector3,
}

type Pursuit = {
	userId: number,
	cops: { Cop },
	speedingFor: number,
	-- Verhindert, dass zwei Beamte gleichzeitig verhaften.
	arrestInProgress: boolean,
}

local PoliceService = {}

local pursuits: { [number]: Pursuit } = {}
local copFolder: Folder

local PATH_REFRESH_SECONDS = 1.2
local STUCK_DISTANCE = 3
local STUCK_TIMEOUT = 4

-- ============================================================
-- Intern
-- ============================================================

local function characterOf(userId: number): (Player?, Model?, BasePart?)
	local player = Players:GetPlayerByUserId(userId)
	if not player then
		return nil, nil, nil
	end

	local character = player.Character
	if not character then
		return player, nil, nil
	end

	local root = character:FindFirstChild("HumanoidRootPart") :: BasePart?
	return player, character, root
end

--[[
	Sucht Boden unter einer Stelle und liefert eine Einsatzposition.
	Gibt nil zurueck, wenn dort nichts ist - dann wird nicht gespawnt,
	statt einen Beamten ins Leere fallen zu lassen.
]]
local function groundAt(position: Vector3, ignore: { Instance }): Vector3?
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = ignore

	local result = Workspace:Raycast(position + Vector3.new(0, 120, 0), Vector3.new(0, -400, 0), params)
	return if result then result.Position + Vector3.new(0, 3, 0) else nil
end

--[[ Sichtlinie vom Kopf des Beamten zum Ziel. ]]
local function hasLineOfSight(cop: Cop, targetRoot: BasePart, range: number): boolean
	local origin = cop.root.Position + Vector3.new(0, 1.5, 0)
	local delta = targetRoot.Position - origin
	local distance = delta.Magnitude

	if distance > range then
		return false
	end

	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { cop.model, copFolder }

	local result = Workspace:Raycast(origin, delta, params)
	if not result then
		return true
	end

	-- Treffer auf dem Ziel selbst oder auf dessen Fahrzeug zaehlt als Sicht.
	return result.Instance:IsDescendantOf(targetRoot.Parent :: Instance)
		or VehicleService.getRecordFromPart(result.Instance) ~= nil
end

local function despawnCop(cop: Cop)
	cop.model:Destroy()
end

local function spawnCop(pursuit: Pursuit, targetRoot: BasePart): Cop?
	local angle = math.random() * math.pi * 2
	local distance = Config.Police.SpawnDistance * (0.6 + math.random() * 0.4)
	local candidate = targetRoot.Position + Vector3.new(math.cos(angle) * distance, 0, math.sin(angle) * distance)

	local ground = groundAt(candidate, { copFolder, targetRoot.Parent :: Instance })
	if not ground then
		return nil
	end

	local model = CopFactory.build(CFrame.new(ground))
	model.Parent = copFolder

	local humanoid = model:FindFirstChildOfClass("Humanoid")
	local root = model:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not humanoid or not root then
		model:Destroy()
		return nil
	end

	local cop: Cop = {
		model = model,
		humanoid = humanoid,
		root = root,
		targetUserId = pursuit.userId,
		waypoints = {},
		waypointIndex = 1,
		lastPathAt = 0,
		arrestHold = 0,
		stuckSince = os.clock(),
		lastPosition = root.Position,
	}

	return cop
end

--[[
	Berechnet einen Weg zum Ziel. Faellt auf direktes MoveTo zurueck, wenn
	die Wegfindung scheitert - lieber ein Beamter, der gegen eine Wand
	laeuft, als einer, der stehen bleibt und die Jagd langweilig macht.
]]
local function repath(cop: Cop, goal: Vector3)
	cop.lastPathAt = os.clock()

	local path = PathfindingService:CreatePath({
		AgentRadius = 2,
		AgentHeight = 5,
		AgentCanJump = true,
		WaypointSpacing = 6,
	})

	local ok = pcall(function()
		path:ComputeAsync(cop.root.Position, goal)
	end)

	if ok and path.Status == Enum.PathStatus.Success then
		cop.waypoints = path:GetWaypoints()
		cop.waypointIndex = 2 -- der erste Punkt ist die eigene Position
	else
		cop.waypoints = {}
		cop.waypointIndex = 1
		cop.humanoid:MoveTo(goal)
	end
end

local function followPath(cop: Cop, goal: Vector3)
	if #cop.waypoints == 0 then
		cop.humanoid:MoveTo(goal)
		return
	end

	local waypoint = cop.waypoints[cop.waypointIndex]
	if not waypoint then
		cop.waypoints = {}
		cop.humanoid:MoveTo(goal)
		return
	end

	local flatDelta = (waypoint.Position - cop.root.Position) * Vector3.new(1, 0, 1)
	if flatDelta.Magnitude < 4 then
		cop.waypointIndex += 1
		waypoint = cop.waypoints[cop.waypointIndex]
		if not waypoint then
			return
		end
	end

	if waypoint.Action == Enum.PathWaypointAction.Jump then
		cop.humanoid.Jump = true
	end

	cop.humanoid:MoveTo(waypoint.Position)
end

local function arrest(pursuit: Pursuit, player: Player)
	if pursuit.arrestInProgress then
		return
	end
	pursuit.arrestInProgress = true

	local lost = EconomyService.forfeit(player, Config.Economy.CashLossOnArrest, "arrest")
	WantedService.clear(player, "arrest")

	local data = DataService.get(player)
	if data then
		data.stats.arrests += 1
	end

	Net.event("Notify"):FireClient(player, `Verhaftet. Beschlagnahmt: {lost}`, "arrest")

	-- Zurueck an den Spawnpunkt statt Gefaengniszelle: eine Zelle braucht
	-- eine gebaute Karte, die dieses Projekt nicht mitliefert.
	local character = player.Character
	if character then
		local humanoid = character:FindFirstChildOfClass("Humanoid")
		if humanoid and humanoid.SeatPart then
			humanoid.Sit = false
		end

		local spawnLocation = Workspace:FindFirstChildOfClass("SpawnLocation")
		if spawnLocation then
			-- Erst abmelden, dann versetzen: sonst meldet die eigene
			-- Verhaftung einen Teleport und der Spieler faengt sich einen
			-- Anti-Cheat-Verstoss fuer etwas ein, das der Server getan hat.
			AntiCheatService.excuse(player, 5)
			task.wait(0.2)
			character:PivotTo(spawnLocation.CFrame + Vector3.new(0, 4, 0))
		end
	end

	pursuit.arrestInProgress = false
end

-- ============================================================
-- Denkschritt
-- ============================================================

local function updatePursuit(pursuit: Pursuit, deltaTime: number)
	local player, character, targetRoot = characterOf(pursuit.userId)

	-- Ziel weg oder tot: Einsatz beenden.
	if not player or not character or not targetRoot then
		for _, cop in pursuit.cops do
			despawnCop(cop)
		end
		pursuits[pursuit.userId] = nil
		return
	end

	local stars = WantedService.getStars(player)
	if stars <= 0 then
		for _, cop in pursuit.cops do
			despawnCop(cop)
		end
		pursuits[pursuit.userId] = nil
		return
	end

	local desired = WantedService.desiredCopCount(player)
	local sightRange = WantedService.sightRange(player)

	-- Bestand auf Soll bringen. Pro Denkschritt hoechstens ein Beamter,
	-- damit bei einem Sprung von 0 auf 5 Sternen nicht acht Rigs in
	-- einem Frame entstehen.
	if #pursuit.cops < desired then
		local cop = spawnCop(pursuit, targetRoot)
		if cop then
			table.insert(pursuit.cops, cop)
		end
	elseif #pursuit.cops > desired then
		local cop = table.remove(pursuit.cops)
		if cop then
			despawnCop(cop)
		end
	end

	local anySight = false
	local targetSpeed = VehicleService.getSpeedOf(player)

	for index = #pursuit.cops, 1, -1 do
		local cop = pursuit.cops[index]

		if not cop.model.Parent or cop.humanoid.Health <= 0 then
			table.remove(pursuit.cops, index)
			despawnCop(cop)
			continue
		end

		local distance = (cop.root.Position - targetRoot.Position).Magnitude

		-- Zu weit abgehaengt: neu einsetzen statt quer ueber die Karte
		-- hinterherlaufen zu lassen.
		if distance > Config.Police.SpawnDistance * 2.5 then
			table.remove(pursuit.cops, index)
			despawnCop(cop)
			continue
		end

		if hasLineOfSight(cop, targetRoot, sightRange) then
			anySight = true
		end

		-- Festgefahren? Neuer Weg.
		if (cop.root.Position - cop.lastPosition).Magnitude < STUCK_DISTANCE then
			if os.clock() - cop.stuckSince > STUCK_TIMEOUT then
				cop.lastPathAt = 0
				cop.stuckSince = os.clock()
			end
		else
			cop.stuckSince = os.clock()
			cop.lastPosition = cop.root.Position
		end

		if os.clock() - cop.lastPathAt > PATH_REFRESH_SECONDS then
			repath(cop, targetRoot.Position)
		else
			followPath(cop, targetRoot.Position)
		end

		-- Verhaftung nur, wenn das Ziel praktisch steht. Ein Beamter, der
		-- ein Auto mit 120 Studs/s im Vorbeilaufen verhaftet, waere Unsinn.
		if distance <= Config.Police.ArrestDistance and targetSpeed < 15 then
			cop.arrestHold += deltaTime
			if cop.arrestHold >= Config.Police.ArrestHoldSeconds then
				cop.arrestHold = 0
				task.spawn(arrest, pursuit, player)
			end
		else
			cop.arrestHold = 0
		end
	end

	if anySight then
		WantedService.markSeen(player)

		if targetSpeed > Config.Police.SpeedLimit then
			pursuit.speedingFor += deltaTime
			if pursuit.speedingFor >= Config.Police.SpeedingGraceSeconds then
				pursuit.speedingFor = 0
				WantedService.addOffence(player, "Speeding")
			end
		else
			pursuit.speedingFor = 0
		end
	else
		pursuit.speedingFor = 0
	end
end

-- ============================================================
-- Start
-- ============================================================

function PoliceService.init()
	copFolder = Workspace:FindFirstChild("Police") :: Folder
	if not copFolder then
		copFolder = Instance.new("Folder")
		copFolder.Name = "Police"
		copFolder.Parent = Workspace
	end
end

function PoliceService.start()
	WantedService.StarsChanged:Connect(function(player: Player, stars: number)
		if stars > 0 and not pursuits[player.UserId] then
			pursuits[player.UserId] = {
				userId = player.UserId,
				cops = {},
				speedingFor = 0,
				arrestInProgress = false,
			}
		end
	end)

	Players.PlayerRemoving:Connect(function(player)
		local pursuit = pursuits[player.UserId]
		if pursuit then
			for _, cop in pursuit.cops do
				despawnCop(cop)
			end
			pursuits[player.UserId] = nil
		end
	end)

	task.spawn(function()
		while true do
			local deltaTime = task.wait(Config.Police.ThinkInterval)

			for _, pursuit in pursuits do
				local ok, err = pcall(updatePursuit, pursuit, deltaTime)
				if not ok then
					warn(`[Police] Denkschritt gescheitert: {err}`)
				end
			end
		end
	end)
end

return PoliceService
