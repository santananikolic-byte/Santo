--!strict
--[[
	WorldService
	Baut eine schlichte Testkarte, falls die Baustelle leer ist.

	Das ist ausdruecklich kein Level-Design, sondern ein Geruest: ein
	Strassenraster mit Bloecken dazwischen, damit Wegfindung, Verfolgung
	und Fahrphysik direkt nach dem Sync etwas zum Arbeiten haben. Sobald
	eine echte Karte im Platz liegt, findet dieser Service sie vor und
	haelt sich raus.
]]

local Workspace = game:GetService("Workspace")

local WorldService = {}

local BLOCK_SIZE = 120
local ROAD_WIDTH = 40
local GRID = 4 -- GRID x GRID Baubloecke

local function part(name: string, size: Vector3, cframe: CFrame, colour: Color3, parent: Instance): BasePart
	local instance = Instance.new("Part")
	instance.Name = name
	instance.Size = size
	instance.CFrame = cframe
	instance.Anchored = true
	instance.Color = colour
	instance.Material = Enum.Material.Concrete
	instance.TopSurface = Enum.SurfaceType.Smooth
	instance.BottomSurface = Enum.SurfaceType.Smooth
	instance.Parent = parent
	return instance
end

local function buildCity(parent: Folder)
	local span = GRID * (BLOCK_SIZE + ROAD_WIDTH)

	-- Asphalt als eine Flaeche. Ein Raster aus einzelnen Strassenteilen
	-- saehe besser aus, kostet aber ohne Not hunderte Teile.
	local ground = part(
		"Ground",
		Vector3.new(span + 200, 4, span + 200),
		CFrame.new(0, -2, 0),
		Color3.fromRGB(48, 48, 52),
		parent
	)
	ground.Material = Enum.Material.Asphalt

	local half = (GRID - 1) / 2

	for x = 0, GRID - 1 do
		for z = 0, GRID - 1 do
			local centreX = (x - half) * (BLOCK_SIZE + ROAD_WIDTH)
			local centreZ = (z - half) * (BLOCK_SIZE + ROAD_WIDTH)

			-- Gehweg
			part(
				"Sidewalk",
				Vector3.new(BLOCK_SIZE, 1.2, BLOCK_SIZE),
				CFrame.new(centreX, 0.6, centreZ),
				Color3.fromRGB(150, 150, 155),
				parent
			)

			-- Gebaeude, etwas kleiner als der Block, damit ringsum Gehweg
			-- bleibt. Deterministische Hoehe ueber die Rasterposition:
			-- so sieht die Karte bei jedem Serverstart gleich aus.
			local height = 40 + ((x * 7 + z * 13) % 5) * 26
			local footprint = BLOCK_SIZE - 26

			local building = part(
				"Building",
				Vector3.new(footprint, height, footprint),
				CFrame.new(centreX, height / 2 + 1.2, centreZ),
				Color3.fromRGB(70 + (x * 23) % 60, 74 + (z * 17) % 55, 88),
				parent
			)
			building.Material = Enum.Material.Brick
		end
	end
end

function WorldService.init()
	local existing = Workspace:FindFirstChild("City")
	if existing then
		return
	end

	-- Vorhandene Karte respektieren: alles ausser dem Standard-Baseplate
	-- gilt als bewusst gebaut.
	-- Was ein frischer Baseplate-Platz von Haus aus mitbringt, zaehlt
	-- nicht als selbstgebaute Karte. Ohne diese Ausnahme haelt sich der
	-- Service wegen der Standard-SpawnLocation fuer ueberfluessig und die
	-- Teststadt entsteht nie.
	local STOCK = { Baseplate = true, SpawnLocation = true, Terrain = true, Camera = true }

	local hasCustomGeometry = false
	for _, child in Workspace:GetChildren() do
		if STOCK[child.Name] then
			continue
		end
		if child:IsA("BasePart") or child:IsA("Model") then
			hasCustomGeometry = true
			break
		end
	end

	if hasCustomGeometry then
		return
	end

	for _, name in { "Baseplate", "SpawnLocation" } do
		local stock = Workspace:FindFirstChild(name)
		if stock then
			stock:Destroy()
		end
	end

	local city = Instance.new("Folder")
	city.Name = "City"
	city.Parent = Workspace

	buildCity(city)

	if not Workspace:FindFirstChildOfClass("SpawnLocation") then
		local spawnLocation = Instance.new("SpawnLocation")
		spawnLocation.Name = "CitySpawn"
		spawnLocation.Size = Vector3.new(24, 1, 24)
		spawnLocation.CFrame = CFrame.new(0, 1.5, 0)
		spawnLocation.Anchored = true
		spawnLocation.Color = Color3.fromRGB(90, 200, 255)
		spawnLocation.Material = Enum.Material.Neon
		spawnLocation.Parent = city
	end
end

function WorldService.start() end

return WorldService
