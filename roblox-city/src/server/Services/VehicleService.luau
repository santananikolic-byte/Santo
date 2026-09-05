--!strict
--[[
	VehicleService
	Besitz, Einsetzen, Antrieb und Aufraeumen aller Fahrzeuge.

	Aufteilung der Zustaendigkeiten:

	  Client   -> Eingabe. Gas, Lenkung, Handbremse. Mehr nicht.
	  Server   -> Antrieb, Besitz, Diebstahl, Aufraeumen.

	Der Server liest Throttle und Steer aus dem VehicleSeat, den der Fahrer
	besetzt, und setzt daraus die Constraints. Der Client kann diese Werte
	nur zwischen -1 und 1 bewegen; die Uebersetzung in Drehzahl und
	Lenkwinkel passiert hier. Ein Exploiter, der ThrottleFloat auf 500
	setzt, bekommt trotzdem nur Vollgas.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)
local Signal = require(ReplicatedStorage.Shared.Signal)
local Util = require(ReplicatedStorage.Shared.Util)

local DataService = require(script.Parent.Parent.Data.DataService)
local VehicleFactory = require(script.Parent.VehicleFactory)
local WantedService = require(script.Parent.WantedService)

type Record = {
	model: Model,
	chassis: BasePart,
	driverSeat: VehicleSeat,
	modelKey: string,
	plate: string,
	-- 0 = herrenlos (Streifenwagen, Strassenfund), sonst UserId des Besitzers.
	ownerUserId: number,
	servos: { HingeConstraint },
	motors: { HingeConstraint },
	topSpeed: number,
	acceleration: number,
	grip: number,
	-- os.clock() des letzten Moments mit Fahrer.
	lastOccupied: number,
	currentDriver: Player?,
}

local VehicleService = {}

-- (player, record) wenn jemand ein fremdes Fahrzeug uebernimmt
VehicleService.VehicleStolen = Signal.new()

local records: { [Model]: Record } = {}
local activeCount = 0
local plateCounter = 0
local vehicleFolder: Folder

-- ============================================================
-- Intern
-- ============================================================

local function nextPlate(): string
	plateCounter += 1
	return string.format("%s-%03d", string.char(65 + (plateCounter % 26)), plateCounter % 1000)
end

local function collectConstraints(model: Model): ({ HingeConstraint }, { HingeConstraint })
	local servos: { HingeConstraint } = {}
	local motors: { HingeConstraint } = {}

	local drivetrain = model:FindFirstChild("Drivetrain")
	if not drivetrain then
		return servos, motors
	end

	for _, child in drivetrain:GetChildren() do
		if child:IsA("HingeConstraint") then
			if child.ActuatorType == Enum.ActuatorType.Servo then
				table.insert(servos, child)
			elseif child.ActuatorType == Enum.ActuatorType.Motor then
				table.insert(motors, child)
			end
		end
	end

	return servos, motors
end

local function destroyVehicle(record: Record)
	if records[record.model] == nil then
		return
	end

	records[record.model] = nil
	activeCount = math.max(0, activeCount - 1)
	record.model:Destroy()
end

--[[ Sucht den Datensatz zu einem beliebigen Teil eines Fahrzeugs. ]]
local function recordFromDescendant(instance: Instance?): Record?
	local cursor = instance
	while cursor do
		if cursor:IsA("Model") and records[cursor] then
			return records[cursor]
		end
		cursor = cursor.Parent
	end
	return nil
end

-- ============================================================
-- Antrieb
-- ============================================================

--[[
	Ein Schritt der Fahrphysik fuer ein Fahrzeug.

	Das Drehmoment faellt zum Hoechsttempo hin ab, statt hart abgeriegelt zu
	werden. Ein harter Riegel fuehlt sich an, als wuerde man gegen eine Wand
	fahren; ein abfallendes Moment fuehlt sich nach Motor an.
]]
local function stepVehicle(record: Record, deltaTime: number)
	local seat = record.driverSeat
	local occupant = seat.Occupant

	if not occupant then
		-- Ausrollen lassen, nicht abrupt stoppen.
		for _, motor in record.motors do
			motor.AngularVelocity = 0
			motor.MotorMaxTorque = 0
		end
		for _, servo in record.servos do
			servo.TargetAngle = 0
		end
		return
	end

	-- Eingaben klemmen. Die Werte kommen vom Client des Fahrers.
	local throttle = math.clamp(seat.ThrottleFloat, -1, 1)
	local steer = math.clamp(seat.SteerFloat, -1, 1)

	if not Util.isFiniteNumber(throttle) then
		throttle = 0
	end
	if not Util.isFiniteNumber(steer) then
		steer = 0
	end

	local velocity = record.chassis.AssemblyLinearVelocity
	local speed = velocity.Magnitude

	-- Lenkeinschlag wird mit dem Tempo kleiner. Bei 140 Studs/s voll
	-- einzuschlagen wuerde das Fahrzeug ueberschlagen.
	local steerScale = math.clamp(1 - (speed / (record.topSpeed * 1.2)), 0.25, 1)
	local targetAngle = steer * 35 * steerScale

	for _, servo in record.servos do
		servo.TargetAngle = targetAngle
		servo.AngularSpeed = 6 + record.grip * 4
	end

	-- Raddrehzahl aus Wunschtempo: Umfang = 2*pi*r, also
	-- Winkelgeschwindigkeit = Bahngeschwindigkeit / Radius.
	local desiredSpeed = throttle * record.topSpeed
	local wheelVelocity = desiredSpeed / VehicleFactory.WHEEL_RADIUS

	local speedRatio = math.clamp(speed / record.topSpeed, 0, 1)
	local torqueFalloff = 1 - speedRatio ^ 2
	local torque = record.acceleration * 1200 * math.max(torqueFalloff, 0.08)

	-- Bremsen: Gas entgegen der Fahrtrichtung gibt volles Moment.
	local forward = record.chassis.CFrame.LookVector
	local forwardSpeed = velocity:Dot(forward)
	local braking = (throttle < -0.05 and forwardSpeed > 1) or (throttle > 0.05 and forwardSpeed < -1)
	if braking then
		torque = record.acceleration * 2600
	end

	for _, motor in record.motors do
		motor.AngularVelocity = wheelVelocity
		motor.MotorMaxTorque = torque
	end

	record.lastOccupied = os.clock()

	local driver = Players:GetPlayerFromCharacter(occupant.Parent)
	if driver then
		local data = DataService.get(driver)
		if data then
			data.stats.metersDriven += speed * deltaTime
		end
	end
end

-- ============================================================
-- Sitze
-- ============================================================

local function onDriverSeated(record: Record, player: Player)
	record.currentDriver = player
	record.lastOccupied = os.clock()

	-- Netzwerkbesitz an den Fahrer: ohne das ruckelt jedes Fahrzeug, weil
	-- die Physik auf dem Server laeuft und die Eingabe eine Runde spaeter
	-- ankommt. Die Wirtschaft bleibt trotzdem serverseitig - der Client
	-- besitzt die Physik, nicht die Wahrheit ueber Geld oder Fahndung.
	pcall(function()
		record.chassis:SetNetworkOwner(player)
	end)

	if record.ownerUserId ~= 0 and record.ownerUserId ~= player.UserId then
		WantedService.addOffence(player, "VehicleTheft")
		VehicleService.VehicleStolen:Fire(player, record)
		Net.event("Notify"):FireClient(player, "Fahrzeugdiebstahl gemeldet.", "warning")
	end
end

local function onDriverLeft(record: Record)
	record.currentDriver = nil
	record.lastOccupied = os.clock()

	pcall(function()
		record.chassis:SetNetworkOwnershipAuto()
	end)

	for _, motor in record.motors do
		motor.AngularVelocity = 0
		motor.MotorMaxTorque = 0
	end
end

-- ============================================================
-- Oeffentliche API
-- ============================================================

--[[
	Setzt ein Fahrzeug in die Welt.

	ownerUserId 0 bedeutet herrenlos - Streifenwagen und Strassenfunde.
]]
function VehicleService.spawn(modelKey: string, cframe: CFrame, ownerUserId: number): Record?
	if activeCount >= Config.Vehicles.MaxActiveVehicles then
		-- Aeltestes herrenloses Fahrzeug opfern, bevor abgelehnt wird.
		local oldest: Record? = nil
		for _, record in records do
			if record.ownerUserId == 0 and not record.currentDriver then
				if not oldest or record.lastOccupied < oldest.lastOccupied then
					oldest = record
				end
			end
		end

		if oldest then
			destroyVehicle(oldest)
		else
			warn("[Vehicle] Fahrzeuglimit erreicht und nichts zum Aufraeumen da")
			return nil
		end
	end

	local spec = Config.Vehicles.Catalog[modelKey]
	if not spec then
		return nil
	end

	local plate = nextPlate()
	local model = VehicleFactory.build(modelKey, cframe, plate)
	if not model then
		return nil
	end

	local chassis = model:FindFirstChild("Chassis") :: BasePart?
	local driverSeat = model:FindFirstChild("DriverSeat") :: VehicleSeat?
	if not chassis or not driverSeat then
		model:Destroy()
		warn(`[Vehicle] Bauplan fuer "{modelKey}" ist unvollstaendig`)
		return nil
	end

	local servos, motors = collectConstraints(model)

	local record: Record = {
		model = model,
		chassis = chassis,
		driverSeat = driverSeat,
		modelKey = modelKey,
		plate = plate,
		ownerUserId = ownerUserId,
		servos = servos,
		motors = motors,
		topSpeed = spec.TopSpeed,
		acceleration = spec.Acceleration,
		grip = spec.HandlingGrip,
		lastOccupied = os.clock(),
		currentDriver = nil,
	}

	model:SetAttribute("OwnerUserId", ownerUserId)
	model.Parent = vehicleFolder

	records[model] = record
	activeCount += 1

	driverSeat:GetPropertyChangedSignal("Occupant"):Connect(function()
		local occupant = driverSeat.Occupant
		if occupant then
			local player = Players:GetPlayerFromCharacter(occupant.Parent)
			if player then
				onDriverSeated(record, player)
			end
		else
			onDriverLeft(record)
		end
	end)

	return record
end

function VehicleService.getRecord(model: Model): Record?
	return records[model]
end

function VehicleService.getRecordFromPart(part: Instance?): Record?
	return recordFromDescendant(part)
end

--[[ Fahrzeug, in dem der Spieler gerade sitzt. ]]
function VehicleService.getVehicleOf(player: Player): Record?
	local character = player.Character
	if not character then
		return nil
	end

	local humanoid = character:FindFirstChildOfClass("Humanoid")
	if not humanoid or not humanoid.SeatPart then
		return nil
	end

	return recordFromDescendant(humanoid.SeatPart)
end

--[[ Geschwindigkeit des Spielers in Studs/s, zu Fuss oder im Fahrzeug. ]]
function VehicleService.getSpeedOf(player: Player): number
	local record = VehicleService.getVehicleOf(player)
	if record then
		return record.chassis.AssemblyLinearVelocity.Magnitude
	end

	local character = player.Character
	local root = character and character:FindFirstChild("HumanoidRootPart") :: BasePart?
	return if root then root.AssemblyLinearVelocity.Magnitude else 0
end

-- ============================================================
-- Remote-Handler
-- ============================================================

local function requestSpawnVehicle(player: Player, modelKey: any): (boolean, any)
	if type(modelKey) ~= "string" then
		return false, "Ungueltiges Modell"
	end

	local data = DataService.get(player)
	if not data then
		return false, "Profil nicht geladen"
	end

	-- Nur Fahrzeuge aus dem eigenen Fuhrpark. Der Katalogschluessel allein
	-- reicht nicht: sonst spawnt sich jeder den Sportwagen frei.
	local owned = nil
	for _, entry in data.vehicles do
		if entry.model == modelKey then
			owned = entry
			break
		end
	end

	if not owned then
		return false, "Dieses Fahrzeug gehoert dir nicht"
	end

	local character = player.Character
	local root = character and character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not root then
		return false, "Kein Charakter in der Welt"
	end

	-- Bereits eingesetzte Fahrzeuge desselben Spielers entfernen, damit
	-- niemand den Fuhrpark als Barrikade benutzt.
	for _, record in records do
		if record.ownerUserId == player.UserId and not record.currentDriver then
			destroyVehicle(record)
		end
	end

	-- Vor dem Spieler absetzen, in dieselbe Richtung schauend.
	--
	-- Die Blickrichtung wird flachgelegt: schaut der Spieler nach oben oder
	-- unten, soll das Fahrzeug trotzdem waagerecht auf der Strasse stehen
	-- und nicht mit der Nase im Boden.
	local facing = root.CFrame.LookVector * Vector3.new(1, 0, 1)
	if facing.Magnitude < 0.01 then
		-- Spieler schaut senkrecht: irgendeine waagerechte Richtung nehmen.
		facing = Vector3.new(0, 0, -1)
	end
	facing = facing.Unit

	local spawnPosition = root.Position + facing * 12
	local spawnCFrame = CFrame.lookAt(spawnPosition, spawnPosition + facing)

	local record = VehicleService.spawn(modelKey, spawnCFrame, player.UserId)
	if not record then
		return false, "Fahrzeug konnte nicht eingesetzt werden"
	end

	Net.event("VehicleSpawned"):FireClient(player, record.plate, modelKey)
	return true, { plate = record.plate, model = modelKey }
end

local function requestEnterVehicle(player: Player, seatPart: any): (boolean, any)
	if typeof(seatPart) ~= "Instance" or not seatPart:IsA("BasePart") then
		return false, "Ungueltiger Sitz"
	end

	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	local root = character and character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not humanoid or not root or humanoid.Health <= 0 then
		return false, "Kein lebender Charakter"
	end

	-- Entfernung serverseitig pruefen. Der Client fragt nur nach; ohne
	-- diese Pruefung koennte er sich in jeden Sitz der Karte setzen.
	local distance = (seatPart.Position - root.Position).Magnitude
	if distance > Config.Vehicles.InteractDistance then
		return false, "Zu weit entfernt"
	end

	local record = recordFromDescendant(seatPart)
	if not record then
		return false, "Kein Fahrzeug"
	end

	local seat = seatPart :: Seat
	if seat.Occupant then
		return false, "Platz besetzt"
	end

	seat:Sit(humanoid)
	return true, { plate = record.plate }
end

local function requestExitVehicle(player: Player)
	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	if humanoid and humanoid.SeatPart then
		humanoid.Sit = false
	end
end

-- ============================================================
-- Start
-- ============================================================

function VehicleService.init()
	vehicleFolder = Workspace:FindFirstChild("Vehicles") :: Folder
	if not vehicleFolder then
		vehicleFolder = Instance.new("Folder")
		vehicleFolder.Name = "Vehicles"
		vehicleFolder.Parent = Workspace
	end

	Net.bindFunction("RequestSpawnVehicle", requestSpawnVehicle)
	Net.bindFunction("RequestEnterVehicle", requestEnterVehicle)
	Net.bindEvent("RequestExitVehicle", requestExitVehicle)
end

function VehicleService.start()
	RunService.Heartbeat:Connect(function(deltaTime)
		for model, record in records do
			if not model.Parent then
				records[model] = nil
				activeCount = math.max(0, activeCount - 1)
				continue
			end
			stepVehicle(record, deltaTime)
		end
	end)

	-- Aufraeumen. Getrennt vom Heartbeat, weil ein Durchlauf pro Frame
	-- ueber 60 Fahrzeuge sinnlos waere.
	task.spawn(function()
		while true do
			task.wait(10)
			local now = os.clock()

			for _, record in records do
				if record.currentDriver then
					continue
				end
				if now - record.lastOccupied < Config.Vehicles.AbandonedCleanupSeconds then
					continue
				end

				-- Fahrzeuge mit Besitzer bleiben, solange der Besitzer im
				-- Server ist. Sonst steht sein gekauftes Auto ploetzlich
				-- nicht mehr da, wo er es geparkt hat.
				if record.ownerUserId ~= 0 and Players:GetPlayerByUserId(record.ownerUserId) then
					continue
				end

				destroyVehicle(record)
			end
		end
	end)

	Players.PlayerRemoving:Connect(function(player)
		for _, record in records do
			if record.ownerUserId == player.UserId then
				destroyVehicle(record)
			end
		end
	end)
end

return VehicleService
