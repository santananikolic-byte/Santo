--!strict
--[[
	CopFactory
	Baut einen einsatzfaehigen R6-Beamten aus Grundkoerpern.

	Ein Humanoid braucht eine feste Knochenstruktur, sonst laeuft er nicht:
	die Teilenamen und die Motor6D-Gelenke sind von Roblox vorgegeben, nicht
	frei waehlbar. Deshalb steht der Rig hier ausgeschrieben statt in einer
	Schleife - jede Abweichung an dieser Stelle fuehrt zu einem NPC, der
	zittert, versinkt oder gar nicht erst geht.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Config = require(ReplicatedStorage.Shared.Config)

local UNIFORM = Color3.fromRGB(32, 46, 88)
local SKIN = Color3.fromRGB(226, 188, 155)
local VEST = Color3.fromRGB(18, 22, 40)

local CopFactory = {}

local function makePart(name: string, size: Vector3, colour: Color3, parent: Model): BasePart
	local part = Instance.new("Part")
	part.Name = name
	part.Size = size
	part.Color = colour
	part.Material = Enum.Material.SmoothPlastic
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.Parent = parent
	return part
end

local function joint(name: string, part0: BasePart, part1: BasePart, c0: CFrame, c1: CFrame)
	local motor = Instance.new("Motor6D")
	motor.Name = name
	motor.Part0 = part0
	motor.Part1 = part1
	motor.C0 = c0
	motor.C1 = c1
	motor.Parent = part0
end

--[[ Setzt einen Beamten an die angegebene Stelle. ]]
function CopFactory.build(spawnCFrame: CFrame): Model
	local model = Instance.new("Model")
	model.Name = "Officer"

	local root = makePart("HumanoidRootPart", Vector3.new(2, 2, 1), UNIFORM, model)
	root.Transparency = 1
	root.CanCollide = false

	local torso = makePart("Torso", Vector3.new(2, 2, 1), VEST, model)
	local head = makePart("Head", Vector3.new(2, 1, 1), SKIN, model)
	local leftArm = makePart("Left Arm", Vector3.new(1, 2, 1), SKIN, model)
	local rightArm = makePart("Right Arm", Vector3.new(1, 2, 1), SKIN, model)
	local leftLeg = makePart("Left Leg", Vector3.new(1, 2, 1), UNIFORM, model)
	local rightLeg = makePart("Right Leg", Vector3.new(1, 2, 1), UNIFORM, model)

	local face = Instance.new("Decal")
	face.Name = "face"
	face.Texture = "rbxasset://textures/face.png"
	face.Face = Enum.NormalId.Front
	face.Parent = head

	model.PrimaryPart = root

	-- Standard-R6-Gelenke. Die Werte sind Roblox-Vorgabe.
	joint("RootJoint", root, torso, CFrame.new(0, 0, 0) * CFrame.Angles(-math.pi / 2, 0, math.pi), CFrame.new(0, 0, 0) * CFrame.Angles(-math.pi / 2, 0, math.pi))
	joint("Neck", torso, head, CFrame.new(0, 1, 0) * CFrame.Angles(-math.pi / 2, 0, math.pi), CFrame.new(0, -0.5, 0) * CFrame.Angles(-math.pi / 2, 0, math.pi))
	joint("Right Shoulder", torso, rightArm, CFrame.new(1, 0.5, 0) * CFrame.Angles(0, math.pi / 2, 0), CFrame.new(-0.5, 0.5, 0) * CFrame.Angles(0, math.pi / 2, 0))
	joint("Left Shoulder", torso, leftArm, CFrame.new(-1, 0.5, 0) * CFrame.Angles(0, -math.pi / 2, 0), CFrame.new(0.5, 0.5, 0) * CFrame.Angles(0, -math.pi / 2, 0))
	joint("Right Hip", torso, rightLeg, CFrame.new(1, -1, 0) * CFrame.Angles(0, math.pi / 2, 0), CFrame.new(0.5, 1, 0) * CFrame.Angles(0, math.pi / 2, 0))
	joint("Left Hip", torso, leftLeg, CFrame.new(-1, -1, 0) * CFrame.Angles(0, -math.pi / 2, 0), CFrame.new(-0.5, 1, 0) * CFrame.Angles(0, -math.pi / 2, 0))

	local humanoid = Instance.new("Humanoid")
	humanoid.RigType = Enum.HumanoidRigType.R6
	humanoid.MaxHealth = Config.Police.NpcHealth
	humanoid.Health = Config.Police.NpcHealth
	humanoid.WalkSpeed = Config.Police.NpcWalkSpeed
	-- Kein Namensschild ueber jedem Beamten: bei acht Verfolgern auf dem
	-- Bildschirm ist das nur noch Textbrei.
	humanoid.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
	humanoid.Parent = model

	local nameTag = Instance.new("BillboardGui")
	nameTag.Name = "Rank"
	nameTag.Size = UDim2.fromOffset(120, 24)
	nameTag.StudsOffset = Vector3.new(0, 2, 0)
	nameTag.AlwaysOnTop = false
	nameTag.MaxDistance = 60
	nameTag.Parent = head

	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundTransparency = 1
	label.Font = Enum.Font.GothamMedium
	label.Text = "POLIZEI"
	label.TextColor3 = Color3.fromRGB(120, 180, 255)
	label.TextScaled = true
	label.Parent = nameTag

	-- Erst positionieren, wenn alles zusammengebaut ist: PivotTo auf ein
	-- halbfertiges Modell verteilt die Teile ueber die halbe Karte.
	model:PivotTo(spawnCFrame + Vector3.new(0, 3, 0))

	return model
end

return CopFactory
