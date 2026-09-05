--!strict
--[[
	InteractionController
	Der Kontextknopf: einsteigen, aussteigen.

	Ein einziger Knopf statt ProximityPrompt, weil derselbe Knopf auf dem
	Handy antippbar und am Rechner mit E bedienbar sein soll. ProximityPrompt
	kann das zwar auch, laesst sich aber nicht in die uebrige Oberflaeche
	einpassen und steht bei acht parkenden Autos achtmal im Bild.

	Der Client sucht den naechsten freien Sitz nur, um den Knopf anzuzeigen.
	Ob der Spieler wirklich einsteigen darf, entscheidet der Server erneut.
]]

local ContextActionService = game:GetService("ContextActionService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local Config = require(ReplicatedStorage.Shared.Config)
local Net = require(ReplicatedStorage.Shared.Net)
local UI = require(script.Parent.Parent.UI)
local HudController = require(script.Parent.HudController)

local player = Players.LocalPlayer

local InteractionController = {}

local prompt: TextButton
local nearestSeat: BasePart? = nil
local busy = false

local SCAN_INTERVAL = 0.2

local function humanoid(): Humanoid?
	local character = player.Character
	return if character then character:FindFirstChildOfClass("Humanoid") else nil
end

local function findNearestSeat(): BasePart?
	local character = player.Character
	local root = character and character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not root then
		return nil
	end

	local vehicles = Workspace:FindFirstChild("Vehicles")
	if not vehicles then
		return nil
	end

	local best: BasePart? = nil
	local bestDistance = Config.Vehicles.InteractDistance

	for _, model in vehicles:GetChildren() do
		if not model:IsA("Model") then
			continue
		end

		for _, child in model:GetChildren() do
			if not child:IsA("Seat") and not child:IsA("VehicleSeat") then
				continue
			end

			local seat = child :: Seat
			if seat.Occupant then
				continue
			end

			local distance = (seat.Position - root.Position).Magnitude
			if distance < bestDistance then
				bestDistance = distance
				best = seat
			end
		end
	end

	return best
end

local function enter()
	local seat = nearestSeat
	if not seat or busy then
		return
	end

	-- busy verhindert, dass ein zweiter Tipp waehrend des wartenden
	-- Aufrufs eine weitere Anfrage schickt und ins Rate-Limit laeuft.
	busy = true
	local ok, success, reason = pcall(function()
		return Net.remoteFunction("RequestEnterVehicle"):InvokeServer(seat)
	end)
	busy = false

	if not ok then
		HudController.toast("Verbindung zum Server gestoert.", "error")
	elseif not success and type(reason) == "string" then
		HudController.toast(reason, "warning")
	end
end

local function exit()
	Net.event("RequestExitVehicle"):FireServer()
end

local function onAction(_actionName: string, inputState: Enum.UserInputState)
	if inputState ~= Enum.UserInputState.Begin then
		return Enum.ContextActionResult.Pass
	end

	local currentHumanoid = humanoid()
	if currentHumanoid and currentHumanoid.SeatPart then
		exit()
	else
		enter()
	end

	return Enum.ContextActionResult.Sink
end

function InteractionController.start(screenGui: ScreenGui)
	prompt = UI.button({
		Name = "InteractPrompt",
		Parent = screenGui,
		AnchorPoint = Vector2.new(0.5, 1),
		Position = UDim2.new(0.5, 0, 1, -30),
		Size = UDim2.fromOffset(200, 44),
		Text = "Einsteigen",
		BackgroundTransparency = 0.1,
		Visible = false,
	})

	prompt.Activated:Connect(function()
		onAction("Interact", Enum.UserInputState.Begin)
	end)

	ContextActionService:BindAction("VehicleInteract", onAction, false, Enum.KeyCode.E)

	task.spawn(function()
		while true do
			task.wait(SCAN_INTERVAL)

			local currentHumanoid = humanoid()
			if currentHumanoid and currentHumanoid.SeatPart then
				nearestSeat = nil
				prompt.Text = "Aussteigen"
				prompt.Visible = true
				continue
			end

			nearestSeat = findNearestSeat()
			prompt.Text = "Einsteigen"
			prompt.Visible = nearestSeat ~= nil
		end
	end)
end

return InteractionController
