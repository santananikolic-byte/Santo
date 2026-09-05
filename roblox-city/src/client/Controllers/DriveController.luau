--!strict
--[[
	DriveController
	Fahrsteuerung fuer Touchgeraete.

	Am Rechner erledigt Roblox das schon: WASD schreibt in ThrottleFloat und
	SteerFloat des VehicleSeat. Auf dem Handy dagegen liefert der Standard-
	Daumenstick ein Richtungssignal, das sich zum Fahren schlecht anfuehlt -
	man will Gas und Lenkung getrennt, nicht einen Punkt in einem Kreis.

	Darum: eigene Pedale und Lenktasten, und der Standard-Stick wird
	abgeschaltet, solange jemand am Steuer sitzt. Zwei Steuerungen, die
	gleichzeitig in dasselbe Feld schreiben, ergeben ein Fahrzeug, das
	zuckt.

	Die Lenkung faehrt weich in die Zielstellung statt hart umzuschalten.
	Ein Knopf ist digital, ein Lenkrad nicht.
]]

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local UI = require(script.Parent.Parent.UI)

local player = Players.LocalPlayer

local DriveController = {}

local pad: Frame? = nil
local currentSeat: VehicleSeat? = nil

local steerTarget = 0
local steerCurrent = 0
local throttleTarget = 0

-- Sekunden von Anschlag zu Anschlag.
local STEER_RAMP = 3.2
local THROTTLE_RAMP = 4.5
local throttleCurrent = 0

local controlsModule: any = nil

local function defaultControls(): any
	if controlsModule then
		return controlsModule
	end

	local ok, result = pcall(function()
		local playerScripts = player:WaitForChild("PlayerScripts", 10)
		local playerModule = playerScripts and playerScripts:WaitForChild("PlayerModule", 10)
		return require(playerModule :: ModuleScript)
	end)

	if ok and result then
		controlsModule = result
	end
	return controlsModule
end

local function setDefaultControlsEnabled(enabled: boolean)
	local module = defaultControls()
	if not module then
		return
	end

	pcall(function()
		local controls = module:GetControls()
		if enabled then
			controls:Enable()
		else
			controls:Disable()
		end
	end)
end

-- ============================================================
-- Aufbau
-- ============================================================

local function makeHoldButton(
	parent: Frame,
	name: string,
	text: string,
	position: UDim2,
	size: UDim2,
	onDown: () -> (),
	onUp: () -> ()
): TextButton
	local button = UI.button({
		Name = name,
		Parent = parent,
		Position = position,
		Size = size,
		AnchorPoint = Vector2.new(0.5, 0.5),
		Text = text,
		TextSize = 22,
		BackgroundColor3 = UI.Theme.Panel,
		BackgroundTransparency = 0.15,
		AutoButtonColor = false,
	})

	local function press()
		button.BackgroundColor3 = UI.Theme.Accent
		button.BackgroundTransparency = 0.35
		onDown()
	end

	local function release()
		button.BackgroundColor3 = UI.Theme.Panel
		button.BackgroundTransparency = 0.15
		onUp()
	end

	button.InputBegan:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.Touch or input.UserInputType == Enum.UserInputType.MouseButton1 then
			press()
		end
	end)

	-- InputEnded UND MouseLeave: ein Finger, der vom Knopf rutscht, loest
	-- kein InputEnded auf diesem Knopf aus, und das Gas bliebe stehen.
	button.InputEnded:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.Touch or input.UserInputType == Enum.UserInputType.MouseButton1 then
			release()
		end
	end)
	button.MouseLeave:Connect(release)

	return button
end

local function buildPad(screenGui: ScreenGui): Frame
	local frame = UI.create("Frame", {
		Name = "DrivePad",
		Parent = screenGui,
		Size = UDim2.fromScale(1, 1),
		BackgroundTransparency = 1,
		Visible = false,
	}) :: Frame

	local buttonSize = UDim2.fromOffset(84, 84)

	makeHoldButton(frame, "SteerLeft", "<", UDim2.new(0, 80, 1, -90), buttonSize, function()
		steerTarget -= 1
	end, function()
		steerTarget += 1
	end)

	makeHoldButton(frame, "SteerRight", ">", UDim2.new(0, 184, 1, -90), buttonSize, function()
		steerTarget += 1
	end, function()
		steerTarget -= 1
	end)

	makeHoldButton(frame, "Throttle", "GAS", UDim2.new(1, -80, 1, -90), buttonSize, function()
		throttleTarget += 1
	end, function()
		throttleTarget -= 1
	end)

	makeHoldButton(frame, "Brake", "BREMSE", UDim2.new(1, -184, 1, -90), buttonSize, function()
		throttleTarget -= 1
	end, function()
		throttleTarget += 1
	end)

	return frame
end

-- ============================================================
-- Ablauf
-- ============================================================

local function enterVehicle(seat: VehicleSeat)
	currentSeat = seat
	steerTarget = 0
	throttleTarget = 0
	steerCurrent = 0
	throttleCurrent = 0

	if UserInputService.TouchEnabled then
		if pad then
			pad.Visible = true
		end
		setDefaultControlsEnabled(false)
	end
end

local function exitVehicle()
	local seat = currentSeat
	if seat then
		-- Beim Aussteigen loslassen. Sonst faehrt das Fahrzeug mit dem
		-- letzten Gaswert weiter, bis der Server es ausrollen laesst.
		pcall(function()
			seat.ThrottleFloat = 0
			seat.SteerFloat = 0
		end)
	end

	currentSeat = nil
	steerTarget = 0
	throttleTarget = 0

	if pad then
		pad.Visible = false
	end
	setDefaultControlsEnabled(true)
end

local function watchHumanoid(humanoid: Humanoid)
	humanoid:GetPropertyChangedSignal("SeatPart"):Connect(function()
		local seatPart = humanoid.SeatPart

		if seatPart and seatPart:IsA("VehicleSeat") then
			enterVehicle(seatPart)
		else
			exitVehicle()
		end
	end)
end

function DriveController.isDriving(): boolean
	return currentSeat ~= nil
end

function DriveController.start(screenGui: ScreenGui)
	pad = buildPad(screenGui)

	local function attachCharacter(character: Model)
		local humanoid = character:WaitForChild("Humanoid", 10)
		if humanoid and humanoid:IsA("Humanoid") then
			watchHumanoid(humanoid)
		end
	end

	if player.Character then
		task.spawn(attachCharacter, player.Character)
	end
	player.CharacterAdded:Connect(attachCharacter)
	player.CharacterRemoving:Connect(exitVehicle)

	RunService.RenderStepped:Connect(function(deltaTime)
		local seat = currentSeat
		if not seat or not seat.Parent then
			return
		end

		-- Nur auf Touch selbst schreiben. Am Rechner wuerde das die
		-- Tastatureingabe ueberschreiben, die Roblox schon eintraegt.
		if not UserInputService.TouchEnabled then
			return
		end

		local steerGoal = math.clamp(steerTarget, -1, 1)
		local throttleGoal = math.clamp(throttleTarget, -1, 1)

		steerCurrent += math.clamp(steerGoal - steerCurrent, -deltaTime * STEER_RAMP, deltaTime * STEER_RAMP)
		throttleCurrent += math.clamp(throttleGoal - throttleCurrent, -deltaTime * THROTTLE_RAMP, deltaTime * THROTTLE_RAMP)

		-- Kleine Reste auf null ziehen, sonst schleicht das Fahrzeug
		-- endlos mit 0.03 Gas weiter.
		if math.abs(steerCurrent) < 0.02 then
			steerCurrent = 0
		end
		if math.abs(throttleCurrent) < 0.02 then
			throttleCurrent = 0
		end

		seat.SteerFloat = steerCurrent
		seat.ThrottleFloat = throttleCurrent
	end)
end

return DriveController
