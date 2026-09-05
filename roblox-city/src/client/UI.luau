--!strict
--[[
	UI
	Bausteine und Farben fuer die Oberflaeche.

	Die Oberflaeche entsteht im Code statt als StarterGui-Baum: so laesst
	sie sich versionieren und im Diff lesen. Ein handgebautes ScreenGui in
	der .rbxl-Datei ist im Review unsichtbar.
]]

local UI = {}

UI.Theme = {
	Background = Color3.fromRGB(16, 17, 22),
	Panel = Color3.fromRGB(24, 26, 33),
	PanelBorder = Color3.fromRGB(44, 48, 60),
	Text = Color3.fromRGB(236, 238, 244),
	TextMuted = Color3.fromRGB(150, 156, 172),
	Accent = Color3.fromRGB(92, 190, 255),
	Money = Color3.fromRGB(126, 217, 87),
	Danger = Color3.fromRGB(238, 96, 88),
	Warning = Color3.fromRGB(240, 186, 74),
	Star = Color3.fromRGB(255, 214, 92),
}

UI.Font = Enum.Font.GothamMedium
UI.FontBold = Enum.Font.GothamBold

--[[ Erzeugt eine Instanz und setzt Eigenschaften und Kinder in einem Rutsch. ]]
function UI.create(className: string, properties: { [string]: any }, children: { Instance }?): Instance
	local instance = Instance.new(className)

	for key, value in properties do
		-- Parent immer zuletzt: sonst loest jede weitere Zuweisung eine
		-- eigene Neuberechnung des Layouts aus.
		if key ~= "Parent" then
			(instance :: any)[key] = value
		end
	end

	if children then
		for _, child in children do
			child.Parent = instance
		end
	end

	if properties.Parent then
		instance.Parent = properties.Parent
	end

	return instance
end

function UI.corner(radius: number): UICorner
	return UI.create("UICorner", { CornerRadius = UDim.new(0, radius) }) :: UICorner
end

function UI.stroke(colour: Color3, thickness: number?): UIStroke
	return UI.create("UIStroke", {
		Color = colour,
		Thickness = thickness or 1,
		ApplyStrokeMode = Enum.ApplyStrokeMode.Border,
	}) :: UIStroke
end

function UI.padding(all: number): UIPadding
	return UI.create("UIPadding", {
		PaddingTop = UDim.new(0, all),
		PaddingBottom = UDim.new(0, all),
		PaddingLeft = UDim.new(0, all),
		PaddingRight = UDim.new(0, all),
	}) :: UIPadding
end

--[[ Dunkle Karte mit Rand - die Grundform jedes Panels im Spiel. ]]
function UI.panel(properties: { [string]: any }, children: { Instance }?): Frame
	local merged: { [string]: any } = {
		BackgroundColor3 = UI.Theme.Panel,
		BorderSizePixel = 0,
	}
	for key, value in properties do
		merged[key] = value
	end

	local frame = UI.create("Frame", merged, children) :: Frame
	UI.corner(10).Parent = frame
	UI.stroke(UI.Theme.PanelBorder).Parent = frame
	return frame
end

function UI.label(properties: { [string]: any }): TextLabel
	local merged: { [string]: any } = {
		BackgroundTransparency = 1,
		Font = UI.Font,
		TextColor3 = UI.Theme.Text,
		TextXAlignment = Enum.TextXAlignment.Left,
		TextSize = 16,
	}
	for key, value in properties do
		merged[key] = value
	end
	return UI.create("TextLabel", merged) :: TextLabel
end

function UI.button(properties: { [string]: any }, children: { Instance }?): TextButton
	local merged: { [string]: any } = {
		BackgroundColor3 = UI.Theme.Panel,
		BorderSizePixel = 0,
		Font = UI.FontBold,
		TextColor3 = UI.Theme.Text,
		TextSize = 16,
		AutoButtonColor = true,
	}
	for key, value in properties do
		merged[key] = value
	end

	local button = UI.create("TextButton", merged, children) :: TextButton
	UI.corner(8).Parent = button
	UI.stroke(UI.Theme.PanelBorder).Parent = button
	return button
end

return UI
