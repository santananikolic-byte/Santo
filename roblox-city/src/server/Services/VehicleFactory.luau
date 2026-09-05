--!strict
--[[
	VehicleFactory
	Baut fahrbare Fahrzeuge aus Grundkoerpern, ohne externe Assets.

	Warum aus Teilen statt aus einem Modell aus dem Toolbox-Katalog: das
	Projekt soll direkt nach dem Sync fahren, ohne dass jemand erst
	Assets besorgt. Sobald eigene Modelle da sind, ersetzt man nur diese
	Datei - der Rest des Codes kennt nur `build()` und die Marker darin.

	Aufbau eines Autos:

	    Chassis (Hauptteil, traegt die Masse)
	      |- VehicleSeat            Fahrerplatz, liefert Throttle/Steer
	      |- Passagiersitze
	      |- Hinterraeder           HingeConstraint als Motor  -> Antrieb
	      `- Vorderraeder           zwei Gelenke in Reihe:
	           Servo (senkrecht)    -> Lenkung
	           Motor (waagerecht)   -> Rollen

	Zwei Gelenke in Reihe sind noetig, weil ein HingeConstraint entweder
	lenken oder antreiben kann, nicht beides.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)

local WHEEL_RADIUS = 1.6
local WHEEL_WIDTH = 1.0
local WHEEL_DENSITY = 1.2

-- Umrechnung der Katalogmasse in Roblox-Masse. Bei 9 wiegt eine
-- Limousine mit 1750 im Katalog rund 194 Roblox-Einheiten und damit etwa
-- viermal so viel wie ihre vier Raeder zusammen - ein Verhaeltnis, bei dem
-- das Fahrwerk arbeitet, statt die Karosserie herumzuwerfen.
local MASS_DIVISOR = 9

-- Reifen greifen, Karosserie rutscht. Ohne das kippt das Auto in der Kurve
-- auf die Seite und bleibt auf dem Dach kleben.
local WHEEL_PHYSICS = PhysicalProperties.new(WHEEL_DENSITY, 2.0, 0.1, 100, 1)
local CHASSIS_PHYSICS = PhysicalProperties.new(0.7, 0.2, 0.5, 1, 1)

export type Spec = {
	DisplayName: string,
	Price: number,
	TopSpeed: number,
	Acceleration: number,
	HandlingGrip: number,
	Mass: number,
	Seats: number,
	Body: string,
	Colour: Color3,
	ChassisSize: Vector3,
}

local VehicleFactory = {}

local function attachmentAt(parent: BasePart, name: string, position: Vector3, axis: Vector3): Attachment
	local attachment = Instance.new("Attachment")
	attachment.Name = name
	attachment.Position = position
	attachment.Axis = axis
	attachment.Parent = parent
	return attachment
end

local function makeWheel(name: string, cframe: CFrame, model: Model): BasePart
	local wheel = Instance.new("Part")
	wheel.Name = name
	wheel.Shape = Enum.PartType.Cylinder
	wheel.Size = Vector3.new(WHEEL_WIDTH, WHEEL_RADIUS * 2, WHEEL_RADIUS * 2)
	wheel.CFrame = cframe
	wheel.Color = Color3.fromRGB(28, 28, 30)
	wheel.Material = Enum.Material.SmoothPlastic
	wheel.CustomPhysicalProperties = WHEEL_PHYSICS
	wheel.TopSurface = Enum.SurfaceType.Smooth
	wheel.BottomSurface = Enum.SurfaceType.Smooth
	wheel.Parent = model
	return wheel
end

--[[
	Haengt ein Rad an das Chassis.

	steerable = true erzeugt die Servo-Motor-Kette fuer die Vorderachse.
	Zurueck kommt der Servo (oder nil) und der Antriebsmotor.
]]
local function mountWheel(
	model: Model,
	chassis: BasePart,
	offset: Vector3,
	steerable: boolean,
	driven: boolean
): (HingeConstraint?, HingeConstraint)
	local wheelCFrame = chassis.CFrame * CFrame.new(offset) * CFrame.Angles(0, 0, math.rad(90))
	local wheel = makeWheel(if steerable then "WheelFront" else "WheelRear", wheelCFrame, model)

	-- Die Radachse zeigt seitlich vom Fahrzeug weg.
	local sideSign = if offset.X >= 0 then 1 else -1
	local wheelAxis = Vector3.new(1, 0, 0)

	local steerServo: HingeConstraint? = nil
	local carrier: BasePart = chassis
	local carrierAttachmentPosition = offset

	if steerable then
		-- Zwischenstueck, das sich um die Hochachse dreht.
		local knuckle = Instance.new("Part")
		knuckle.Name = "SteerKnuckle"
		knuckle.Size = Vector3.new(0.4, 0.4, 0.4)
		knuckle.Transparency = 1
		knuckle.CanCollide = false
		knuckle.Massless = true
		knuckle.CFrame = chassis.CFrame * CFrame.new(offset)
		knuckle.Parent = model

		local chassisMount = attachmentAt(chassis, "SteerMountChassis", offset, Vector3.new(0, 1, 0))
		local knuckleMount = attachmentAt(knuckle, "SteerMountKnuckle", Vector3.zero, Vector3.new(0, 1, 0))

		steerServo = Instance.new("HingeConstraint")
		local servo = steerServo :: HingeConstraint
		servo.Name = "SteerServo"
		servo.Attachment0 = chassisMount
		servo.Attachment1 = knuckleMount
		servo.ActuatorType = Enum.ActuatorType.Servo
		servo.ServoMaxTorque = math.huge
		servo.AngularSpeed = 8
		servo.TargetAngle = 0
		servo.LimitsEnabled = true
		servo.LowerAngle = -35
		servo.UpperAngle = 35
		servo.Parent = model

		carrier = knuckle
		carrierAttachmentPosition = Vector3.zero
	end

	local carrierAttachment = attachmentAt(carrier, "WheelMount", carrierAttachmentPosition, wheelAxis * sideSign)
	local wheelAttachment = attachmentAt(wheel, "WheelHub", Vector3.zero, Vector3.new(0, 1, 0) * sideSign)

	local motor = Instance.new("HingeConstraint")
	motor.Name = if driven then "DriveMotor" else "FreeWheel"
	motor.Attachment0 = carrierAttachment
	motor.Attachment1 = wheelAttachment
	motor.ActuatorType = if driven then Enum.ActuatorType.Motor else Enum.ActuatorType.None
	motor.MotorMaxTorque = math.huge
	motor.MotorMaxAcceleration = math.huge
	motor.AngularVelocity = 0
	motor.Parent = model

	return steerServo, motor
end

local function makeSeat(model: Model, chassis: BasePart, index: number, isDriver: boolean, seatCount: number): BasePart
	local seat: BasePart
	if isDriver then
		local vehicleSeat = Instance.new("VehicleSeat")
		-- Die eingebaute Steuerung wird nicht benutzt: Antrieb und Lenkung
		-- laufen ueber die Constraints. Der Sitz liefert nur Throttle und
		-- Steer als Eingabewerte.
		vehicleSeat.MaxSpeed = 0
		vehicleSeat.Torque = 0
		vehicleSeat.TurnSpeed = 0
		seat = vehicleSeat
	else
		seat = Instance.new("Seat")
	end

	seat.Name = if isDriver then "DriverSeat" else `PassengerSeat{index}`
	seat.Size = Vector3.new(2, 0.4, 2)
	seat.Transparency = 1
	seat.CanCollide = false
	seat.Massless = true

	-- Sitzreihen: vorne die ersten zwei, dahinter der Rest.
	local row = if index <= 2 then 1 else 2
	local sideOffset = if index % 2 == 1 then -1.2 else 1.2
	if seatCount == 1 then
		sideOffset = 0
	end
	local depthOffset = if row == 1 then -1.2 else 2.2

	seat.CFrame = chassis.CFrame * CFrame.new(sideOffset, 1.2, depthOffset)
	seat.Parent = model

	local weld = Instance.new("WeldConstraint")
	weld.Part0 = chassis
	weld.Part1 = seat
	weld.Parent = seat

	return seat
end

--[[
	Baut ein fahrbereites Fahrzeug.

	Rueckgabe: das Modell. Die beweglichen Teile sind ueber benannte
	Kinder erreichbar, damit VehicleService keine Struktur raten muss:
	  Chassis, DriverSeat, und der Ordner "Drivetrain" mit den Constraints.
]]
function VehicleFactory.build(modelKey: string, spawnCFrame: CFrame, plate: string): Model?
	local spec = Config.Vehicles.Catalog[modelKey] :: Spec?
	if not spec then
		warn(`[VehicleFactory] Unbekanntes Modell "{modelKey}"`)
		return nil
	end

	local model = Instance.new("Model")
	model.Name = `Vehicle_{modelKey}_{plate}`

	local chassis = Instance.new("Part")
	chassis.Name = "Chassis"
	chassis.Size = spec.ChassisSize
	-- Etwas ueber dem Boden einsetzen, damit die Raeder Platz haben.
	chassis.CFrame = spawnCFrame * CFrame.new(0, WHEEL_RADIUS + 0.6, 0)
	chassis.Color = spec.Colour
	chassis.Material = Enum.Material.Metal
	chassis.CustomPhysicalProperties = CHASSIS_PHYSICS
	chassis.Parent = model
	model.PrimaryPart = chassis

	local halfWidth = spec.ChassisSize.X / 2
	local halfLength = spec.ChassisSize.Z / 2
	local axleY = -spec.ChassisSize.Y / 2

	local drivetrain = Instance.new("Folder")
	drivetrain.Name = "Drivetrain"
	drivetrain.Parent = model

	local servos: { HingeConstraint } = {}
	local motors: { HingeConstraint } = {}

	local isBike = spec.Body == "Bike"
	local wheelPlan: { { offset: Vector3, steerable: boolean, driven: boolean } }

	if isBike then
		wheelPlan = {
			{ offset = Vector3.new(0, axleY, -halfLength + 1), steerable = true, driven = false },
			{ offset = Vector3.new(0, axleY, halfLength - 1), steerable = false, driven = true },
		}
	else
		wheelPlan = {
			{ offset = Vector3.new(-halfWidth, axleY, -halfLength + 1.8), steerable = true, driven = false },
			{ offset = Vector3.new(halfWidth, axleY, -halfLength + 1.8), steerable = true, driven = false },
			{ offset = Vector3.new(-halfWidth, axleY, halfLength - 1.8), steerable = false, driven = true },
			{ offset = Vector3.new(halfWidth, axleY, halfLength - 1.8), steerable = false, driven = true },
		}
	end

	for _, plan in wheelPlan do
		local servo, motor = mountWheel(model, chassis, plan.offset, plan.steerable, plan.driven)
		if servo then
			table.insert(servos, servo)
			servo.Parent = drivetrain
		end
		table.insert(motors, motor)
		motor.Parent = drivetrain
	end

	local seatCount = math.max(1, spec.Seats)
	local driverSeat = makeSeat(model, chassis, 1, true, seatCount)
	for index = 2, seatCount do
		makeSeat(model, chassis, index, false, seatCount)
	end

	-- Kennzeichen als Attribut statt als Instanz: billiger zu replizieren
	-- und der Anti-Cheat kann es ohne Baumsuche lesen.
	model:SetAttribute("Plate", plate)
	model:SetAttribute("Model", modelKey)
	model:SetAttribute("TopSpeed", spec.TopSpeed)

	-- Masse an die Katalogangabe angleichen. Roblox kennt keine Masse,
	-- nur Dichte: Masse = Volumen * Dichte. Wer also eine Zielmasse will,
	-- rechnet Dichte = Zielmasse / Volumen.
	--
	-- MASS_DIVISOR uebersetzt die Katalogangabe (grob Kilogramm, damit die
	-- Zahlen lesbar sind) in Roblox-Masse. Der Teiler kuerzt sich mit dem
	-- Volumen weg, die Verhaeltnisse zwischen den Fahrzeugen bleiben also
	-- exakt die des Katalogs - ein Motorrad ist gegenueber einer Limousine
	-- genau so leicht wie dort angegeben.
	local volume = chassis.Size.X * chassis.Size.Y * chassis.Size.Z
	if volume > 0 then
		local density = math.clamp(spec.Mass / (volume * MASS_DIVISOR), 0.3, 8)
		chassis.CustomPhysicalProperties = PhysicalProperties.new(density, 0.2, 0.5, 1, 1)
	end

	driverSeat:SetAttribute("IsDriverSeat", true)

	return model
end

VehicleFactory.WHEEL_RADIUS = WHEEL_RADIUS

return VehicleFactory
