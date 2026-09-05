--!strict
--[[
	AntiCheatService
	Bewegungspruefung fuer Charaktere.

	Ehrlich vorweg: In Roblox gehoert die Physik des eigenen Charakters dem
	Client. Der Server kann deshalb nicht verhindern, dass jemand seine
	Position setzt - er kann es nur bemerken und rueckgaengig machen. Was
	hier steht, ist eine Heuristik, kein Beweis.

	Deshalb liegt das eigentliche Gewicht dieses Projekts woanders: Geld,
	Fahndung und Auftraege leben komplett auf dem Server. Wer hier durch-
	rutscht, kann sich schnell bewegen - aber kein Geld erzeugen.

	Die Schwellen stehen absichtlich in dieser Datei und nicht in der
	geteilten Config: alles in ReplicatedStorage ist fuer jeden Client
	lesbar, und Grenzwerte, die der Gegner kennt, sind Grenzwerte, an denen
	er entlangfaehrt.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Net = require(ReplicatedStorage.Shared.Net)

local VehicleService = require(script.Parent.VehicleService)

-- Abtastung. Haeufiger waere genauer, kostet aber Rechenzeit pro Spieler.
local SAMPLE_INTERVAL = 0.5

-- Hoechsttempo zu Fuss in Studs/s. Standard-WalkSpeed ist 16; der Puffer
-- deckt Rutschen, Schwung aus Faellen und Netzwerkschwankungen ab.
local MAX_FOOT_SPEED = 34

-- Faktor auf das Hoechsttempo des Fahrzeugs.
local VEHICLE_SPEED_TOLERANCE = 1.6

-- Sprungweite in einem einzelnen Abtastschritt, ab der es ein Teleport ist.
local TELEPORT_DISTANCE = 180

-- Hoehe ueber Grund, ab der ohne Fahrzeug von Fliegen ausgegangen wird.
local FLIGHT_ALTITUDE = 40

-- So viele Abtastschritte in Folge in dieser Hoehe, ohne zu fallen.
local FLIGHT_SAMPLES = 6

-- Verstoesse, bis der Spieler den Server verlaesst.
local VIOLATION_LIMIT = 6

-- Nach dieser Zeit ohne Verstoss faellt der Zaehler wieder.
local VIOLATION_DECAY_SECONDS = 45

type Track = {
	lastPosition: Vector3,
	lastSampleAt: number,
	violations: number,
	lastViolationAt: number,
	airborneSamples: number,
	-- Bis zu diesem Zeitpunkt wird nicht geprueft (Spawn, Verhaftung).
	excuseUntil: number,
}

local AntiCheatService = {}

local tracks: { [number]: Track } = {}

--[[
	Setzt eine Pruefpause. Wird von allem aufgerufen, was den Charakter
	legitim versetzt - sonst meldet die eigene Verhaftung einen Teleport.
]]
function AntiCheatService.excuse(player: Player, seconds: number)
	local track = tracks[player.UserId]
	if track then
		track.excuseUntil = os.clock() + seconds
	end
end

--[[
	Hoehe ueber dem naechsten festen Boden.

	Der eigene Charakter muss aus dem Strahl heraus, sonst trifft er die
	eigenen Beine und liefert immer zwei Studs - die Flugpruefung waere
	damit stillschweigend wirkungslos.
]]
local function heightAboveGround(position: Vector3, character: Model): number
	local ignore: { Instance } = { character }

	local police = Workspace:FindFirstChild("Police")
	if police then
		table.insert(ignore, police)
	end

	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = ignore

	local result = Workspace:Raycast(position, Vector3.new(0, -500, 0), params)
	return if result then (position - result.Position).Magnitude else math.huge
end

local function flag(player: Player, track: Track, reason: string, snapBackTo: Vector3?)
	track.violations += 1
	track.lastViolationAt = os.clock()

	warn(`[AntiCheat] {player.Name}: {reason} ({track.violations}/{VIOLATION_LIMIT})`)

	if snapBackTo then
		local character = player.Character
		if character and character.PrimaryPart then
			character:PivotTo(CFrame.new(snapBackTo))
			-- Nach dem Zurueckversetzen kurz nicht pruefen, sonst meldet
			-- der eigene Eingriff den naechsten Verstoss.
			track.excuseUntil = os.clock() + 1.5
		end
	end

	if track.violations >= VIOLATION_LIMIT then
		player:Kick("Ungewoehnliche Bewegungsdaten. Bitte ohne Drittanbieter-Software erneut beitreten.")
	else
		Net.event("Notify"):FireClient(player, "Bewegung zurueckgesetzt.", "warning")
	end
end

local function sample(player: Player, track: Track, deltaTime: number)
	local character = player.Character
	if not character then
		return
	end

	local root = character:FindFirstChild("HumanoidRootPart") :: BasePart?
	local humanoid = character:FindFirstChildOfClass("Humanoid")
	if not root or not humanoid or humanoid.Health <= 0 then
		return
	end

	local position = root.Position
	local now = os.clock()

	-- Zaehler abklingen lassen: ein einzelner Ausreisser nach einer halben
	-- Stunde sauberem Spiel soll nicht mit einem von vor einer Stunde
	-- zusammenaddiert werden.
	if track.violations > 0 and now - track.lastViolationAt > VIOLATION_DECAY_SECONDS then
		track.violations -= 1
		track.lastViolationAt = now
	end

	if now < track.excuseUntil then
		track.lastPosition = position
		track.airborneSamples = 0
		return
	end

	local delta = position - track.lastPosition
	local horizontal = (delta * Vector3.new(1, 0, 1)).Magnitude
	local speed = horizontal / math.max(deltaTime, 0.001)

	local vehicle = VehicleService.getVehicleOf(player)
	local allowedSpeed = if vehicle then vehicle.topSpeed * VEHICLE_SPEED_TOLERANCE else MAX_FOOT_SPEED

	if delta.Magnitude > TELEPORT_DISTANCE then
		flag(player, track, `Teleport ueber {math.floor(delta.Magnitude)} Studs`, track.lastPosition)
		return
	end

	if speed > allowedSpeed then
		flag(player, track, `Tempo {math.floor(speed)} > {math.floor(allowedSpeed)}`, track.lastPosition)
		return
	end

	-- Flugpruefung. Fallen ist erlaubt, Schweben nicht.
	if not vehicle then
		local verticalVelocity = root.AssemblyLinearVelocity.Y
		local altitude = heightAboveGround(position, character)

		if altitude > FLIGHT_ALTITUDE and verticalVelocity > -6 then
			track.airborneSamples += 1
			if track.airborneSamples >= FLIGHT_SAMPLES then
				track.airborneSamples = 0
				flag(player, track, `Schwebt seit {FLIGHT_SAMPLES} Messungen in {math.floor(altitude)} Studs Hoehe`, track.lastPosition)
				return
			end
		else
			track.airborneSamples = 0
		end
	else
		track.airborneSamples = 0
	end

	track.lastPosition = position
	track.lastSampleAt = now
end

function AntiCheatService.init() end

function AntiCheatService.start()
	local function attach(player: Player)
		tracks[player.UserId] = {
			lastPosition = Vector3.zero,
			lastSampleAt = os.clock(),
			violations = 0,
			lastViolationAt = 0,
			airborneSamples = 0,
			excuseUntil = os.clock() + 5,
		}

		player.CharacterAdded:Connect(function(character)
			local track = tracks[player.UserId]
			if not track then
				return
			end

			local root = character:WaitForChild("HumanoidRootPart", 10) :: BasePart?
			track.lastPosition = if root then root.Position else Vector3.zero
			track.airborneSamples = 0
			-- Beim Spawn faellt der Charakter ein Stueck; ohne Pause waere
			-- jeder Respawn ein gemeldeter Verstoss.
			track.excuseUntil = os.clock() + 4
		end)
	end

	Players.PlayerAdded:Connect(attach)
	for _, player in Players:GetPlayers() do
		attach(player)
	end

	Players.PlayerRemoving:Connect(function(player)
		tracks[player.UserId] = nil
		Net.releasePlayer(player.UserId)
	end)

	task.spawn(function()
		while true do
			local deltaTime = task.wait(SAMPLE_INTERVAL)

			for userId, track in tracks do
				local player = Players:GetPlayerByUserId(userId)
				if not player then
					tracks[userId] = nil
					continue
				end

				local ok, err = pcall(sample, player, track, deltaTime)
				if not ok then
					warn(`[AntiCheat] Messung gescheitert: {err}`)
				end
			end
		end
	end)
end

return AntiCheatService
